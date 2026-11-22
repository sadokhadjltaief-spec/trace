"""The ONLY module the frontend imports from the engine (see docs/INTERFACE.md).

Every function returns plain dicts that validate against engine/contract.py.
State is held in memory per Streamlit server process (sessions dict).

Real: sessions, diagnosis loop (answers + confidence + explanation detector), next-question selection,
tutor hints HINT_1..3 with guards (step 6), entry into RECONSTRUCT / TRANSFER, cost, results reading.
Step 8: RECONSTRUCT/TRANSFER grading, loops, HANDOFF. Step 9: summary(). Study Studio (P1) raises
NotImplementedError; the stub pages use engine/api_fake.py for it.
"""
from __future__ import annotations

import copy
import json
import re
import time
import uuid

from engine import ROOT, bayes, llm, style, tutor
from engine import i18n
from engine.i18n import lang_of, t as tr
from engine import safetext
from engine.config import cfg
from engine.contract import (AnswerRecord, Agenda, Calibration, CourseAnswer, CourseHit, Cost, ExplanationEvidence,
                             Grading, HypProb, LabelProb, LessonRef, MisconceptionView, NextQuestion, QuestionView,
                             SessionState, SessionSummary, SimItemView, SimRun, SimTurn, TutorTurn,
                             GameFeedback, GameRoundView, GameTurn, OutputFile, ReportExport)

_SESSIONS: dict[str, dict] = {}
# TRACE_DEMO=1 (set before starting the server): every LLM call of every feature replays from the cache (offline)
import os as _os  # noqa: E402
FORCED_DEMO = _os.environ.get("TRACE_DEMO") == "1"
if FORCED_DEMO:
    llm.set_demo_mode(True)
_BANK: dict | None = None
_RESULTS_NAME = re.compile(r"^[a-z_]+$")


# ---------------------------------------------------------------- bank / names
def _bank() -> dict:
    global _BANK
    if _BANK is None:
        _BANK = bayes.load_bank()  # excludes crosswalk-blocked questions
    return _BANK


def misconceptions() -> list[dict]:
    out = [MisconceptionView(id="M0", name_en="No misconception found (none of M1-M4)",
                             name_fr="Aucune erreur type détectée", name_ar="لم يُكتشف أي خطأ نمطي").model_dump()]
    for m in _bank()["misconceptions"]:
        out.append(MisconceptionView(id=m["id"], name_en=m["name_en"], name_fr=m.get("name_fr", ""),
                                     name_ar=m.get("name_ar", "")).model_dump())
    return out


def _names() -> dict[str, str]:
    return {m["id"]: m["name_en"] for m in misconceptions()}


# ---------------------------------------------------------------- helpers
def _live_questions() -> tuple[list[dict], list[str]]:
    qs = _bank()["questions"]
    verified = [q for q in qs if q.get("verified")]
    if verified:
        return verified, []
    if cfg().get("live", {}).get("allow_unverified_dev", False):
        return qs, ["Bank not reviewed yet: unverified questions are in use (dev mode)."]
    return [], ["No verified questions in the bank: tick items in data/bank/review.md."]


def _qview(q: dict, profile: dict, lang: str = "en") -> QuestionView:
    structured = bool(profile.get("structured_why"))
    why = []
    if structured:
        why = [safetext.static(tr(k, lang), lang=lang) for k in ("why_rule", "why_steps", "why_example", "why_guess")]
    text, options = i18n.question(q, lang)
    return QuestionView(id=q["id"], text=text, options=options, requires_confidence=True,
                        why_mode="structured" if structured else "free", why_options=why)


def _posterior(d: bayes.Diagnoser) -> list[HypProb]:
    names = _names()
    return [HypProb(id=h, name_en=names[h], prob=round(p, 6)) for h, p in d.as_dict().items()]


def _next(d: bayes.Diagnoser, pool: list[str]) -> NextQuestion:
    nq = d.next_question(pool)
    reason = None
    if nq["stop"]:
        if d.top()[1] >= d.p["stop_threshold"]:
            reason = "threshold"
        elif len(d.asked) >= d.p["max_questions"]:
            reason = "max_questions"
        else:
            reason = "no_questions"
    return NextQuestion(question_id=nq["question"], ig_bits=round(float(nq["ig_bits"]), 4),
                        alternatives=[{"question_id": a["question"], "ig_bits": round(float(a["ig_bits"]), 4)}
                                      for a in nq["alternatives"]],
                        entropy_bits=round(bayes.entropy(d.posterior), 4), stop=nq["stop"], stop_reason=reason)


def _cost(sid: str) -> Cost:
    u = llm.usage_summary(sid)
    rows = u["by_model"]
    return Cost(calls=sum(r["calls"] for r in rows), cached_calls=sum(r["cached_calls"] for r in rows),
                prompt_tokens=sum(r["prompt_tokens"] for r in rows),
                completion_tokens=sum(r["completion_tokens"] for r in rows), label=u["cost_label"] or "")


def _lang(s: dict) -> str:
    return lang_of(s["student"].get("lang"))


def _agenda(s: dict) -> Agenda:
    d = s["diag"]
    total = d.p["max_questions"]
    step = min(len(d.asked) + 1, total)
    return Agenda(step=step, total=total,
                  next=tr("agenda_next_question" if not d.done() else "agenda_results", _lang(s)))


def _state(sid: str) -> SessionState:
    s = _SESSIONS[sid]
    d: bayes.Diagnoser = s["diag"]
    names = _names()
    top_h, top_p = d.top()
    nq = _next(d, s["pool"])
    if s["state"] == "DIAGNOSE":
        cur = s["by_id"].get(nq.question_id) if not nq.stop else None
        cur_view = _qview(cur, s["profile"], _lang(s)) if cur else None
    else:
        qid = s.get("repair_q") if s["state"].startswith("HINT") else (
            s.get("transfer_q") if s["state"] == "TRANSFER" else None)
        cur_view = tutor.qview(s["by_id"][qid], _lang(s)) if qid else None
    return SessionState(session_id=sid, student=s["student"], profile=s["profile"], demo_mode=s["demo"],
                        state=s["state"], agenda=_agenda(s) if s["state"] == "DIAGNOSE" else tutor.agenda(s["state"], _lang(s)),
                        posterior=_posterior(d),
                        top=HypProb(id=top_h, name_en=names[top_h], prob=round(top_p, 6)),
                        asked=s["asked"], current_question=cur_view,
                        next_question=nq, fragile=list(d.fragile), guard_events=s["guard_events"],
                        cost=_cost(sid), warnings=s["warnings"])


# ---------------------------------------------------------------- public API
def start_session(student: dict, profile: dict | None = None, demo: bool = False,
                  detector_llm: bool = True) -> dict:
    sid = uuid.uuid4().hex[:12]
    llm.set_session(sid)
    llm.set_demo_mode(demo or FORCED_DEMO)
    pool, warnings = _live_questions()
    table = bayes.build_table(pool) if pool else bayes.build_table([])
    _SESSIONS[sid] = {"student": {"name": student.get("name", ""), "level": student.get("level", ""),
                                  "lang": student.get("lang", "fr")},
                      "profile": style.resolve(profile), "demo": demo, "state": "DIAGNOSE",
                      "diag": bayes.Diagnoser(table), "pool": [q["id"] for q in pool],
                      "by_id": {q["id"]: q for q in pool}, "asked": [], "guard_events": [], "turn": 0,
                      "warnings": warnings, "created": time.time(), "detector_llm": detector_llm}
    return _state(sid).model_dump()


def get_state(session_id: str) -> dict:
    return _state(session_id).model_dump()


def next_question(session_id: str) -> dict:
    s = _SESSIONS[session_id]
    return _next(s["diag"], s["pool"]).model_dump()


def submit_answer(session_id: str, question_id: str, option: str, confidence: str | None,
                  explanation: str | None = None) -> dict:
    """Record a diagnosis answer. Grading is deterministic (answer key); the posterior update is bayes.py."""
    s = _SESSIONS[session_id]
    if s["state"] != "DIAGNOSE":
        raise ValueError(f"diagnosis is over (state {s['state']}); use tutor_reply")
    q = s["by_id"][question_id]
    if option not in q["options"]:
        raise ValueError(f"unknown option {option!r}")
    if confidence not in ("sure", "unsure"):
        raise ValueError("confidence tap is required: 'sure' or 'unsure'")
    d: bayes.Diagnoser = s["diag"]
    d.observe_answer(question_id, option, confidence)
    correct = option == q["correct"]
    evidence = None
    # free-text "Why?" -> explanation detector -> tempered posterior update (structured choices carry no signal)
    if explanation and explanation.strip() and not s["profile"].get("structured_why"):
        from engine import detector  # lazy: loads the TF-IDF model on first use
        r = detector.detect(q, option, explanation, use_llm=s.get("detector_llm", True))
        d.observe_explanation(r["dist"], {"question": question_id, "method": r["method"], "lang": r["lang"]})
        evidence = ExplanationEvidence(method=r["method"], lang=r["lang"], original=r["original"],
                                       english=r["english"], notes=r["notes"],
                                       dist=[LabelProb(id=k, prob=round(v, 6)) for k, v in r["dist"].items()])
    s["asked"].append(AnswerRecord(question_id=question_id, option=option, confidence=confidence,
                                   correct=correct, explanation=explanation))
    s["turn"] += 1
    nq = _next(d, s["pool"])
    grading = Grading(correct=correct, method="answer_key", label=tr("grade_answer_key", _lang(s)))
    if nq.stop:  # diagnosis over: the state machine takes over (code decides the state and message type)
        h = d.top()[0]
        f = tutor.frame(s, tutor.begin(s, h, _names(), _mis(h), d.as_dict()))
        s["guard_events"] += f.get("guard_events", [])
        turn = TutorTurn(session_id=session_id, turn_id=s["turn"], grading=grading, posterior=_posterior(d),
                         next_question=nq, explanation_evidence=evidence, **f)
        _track(s)
        return turn.model_dump()
    f = tutor.frame(s, {"message": tutor.txt(s, "answer_saved"), "expects": "answer", "agenda": _agenda(s)})
    turn = TutorTurn(session_id=session_id, turn_id=s["turn"], state=s["state"],
                     message=f["message"], expects="answer", agenda=f["agenda"],
                     question=_qview(s["by_id"][nq.question_id], s["profile"], _lang(s)),
                     grading=grading, posterior=_posterior(d), next_question=nq, guard_events=[],
                     explanation_evidence=evidence)
    return turn.model_dump()


def _mis(h: str) -> dict | None:
    return next((m for m in _bank()["misconceptions"] if m["id"] == h), None)


def tutor_reply(session_id: str, text: str | None = None, choice: str | None = None) -> dict:
    """Student reply after a tutor turn.
    HINT_k: `choice` = the retried option. RECONSTRUCT: `choice` = number of the wrong step, `text` = why.
    TRANSFER: `choice` = the option. DONE / HANDOFF: no reply expected (ValueError)."""
    s = _SESSIONS[session_id]
    d: bayes.Diagnoser = s["diag"]
    st = s["state"]
    if st.startswith("HINT"):
        if not choice:
            raise ValueError("a retry needs `choice` (the option letter)")
        s["turn"] += 1
        f, grading = tutor.on_retry(s, choice, _names(), _mis(s["target"]), d.as_dict(), _bank())
        f = tutor.frame(s, f)
        s["guard_events"] += f.get("guard_events", [])
        _track(s)
        return TutorTurn(session_id=session_id, turn_id=s["turn"], grading=grading, posterior=_posterior(d),
                         **f).model_dump()
    if st == "RECONSTRUCT":
        s["turn"] += 1
        f, grading = tutor.on_reconstruct(s, choice, text)
    elif st == "TRANSFER":
        if not choice:
            raise ValueError("a transfer answer needs `choice` (the option letter)")
        s["turn"] += 1
        f, grading = tutor.on_transfer(s, choice, _names(), _bank(), d)
    else:
        raise ValueError(f"no tutor reply expected in state {st}")
    f = tutor.frame(s, f)
    s["guard_events"] += f.get("guard_events", [])
    _track(s)
    return TutorTurn(session_id=session_id, turn_id=s["turn"], grading=grading, posterior=_posterior(d),
                     **f).model_dump()


def _track(s: dict) -> None:
    h = s.setdefault("states", ["DIAGNOSE"])
    if h[-1] != s["state"]:
        h.append(s["state"])




def _handoff_text(s: dict, lang: str, names: dict) -> str | None:
    hd = s.get("handoff_data")
    if not hd:
        return s.get("handoff_note")
    mv = next((m for m in misconceptions() if m["id"] == hd["h"]), None) or {}
    name = mv.get({"fr": "name_fr", "ar": "name_ar"}.get(lang, "name_en")) or names.get(hd["h"], hd["h"])
    return "\n".join([tr("handoff_1", lang, m=name),
                      tr("handoff_2", lang, hints=hd["hints"], loops=hd["loops"],
                         found=tr("found_yes" if hd["found"] else "found_no", lang)),
                      tr("handoff_3", lang, qs=", ".join(hd["wrong"]) or "-")])


def summary(session_id: str, lang: str | None = None) -> dict:
    """One-page report data, built by code from the session (no LLM text), in `lang` (default: the student's)."""
    s = _SESSIONS[session_id]
    d: bayes.Diagnoser = s["diag"]
    names = _names()
    lang = lang_of(lang or _lang(s))
    h = s.get("target") or d.top()[0]
    h = h if h in names else d.top()[0]
    mv = next(m for m in misconceptions() if m["id"] == h)
    status = tutor.mastery_status(s) if "outcome" in s else "in_progress"
    by_id = s["by_id"]

    def res(ok):
        return tr("res_correct" if ok else "res_wrong", lang)
    ev = []
    for a in s["asked"]:
        q = by_id[a.question_id]
        line = tr("ev_answer", lang, q=a.question_id, opt=a.option,
                  conf=tr("conf_sure" if a.confidence == "sure" else "conf_unsure", lang), res=res(a.correct))
        m = q.get("option_misconception", {}).get(a.option)
        if m:
            line += "; " + tr("ev_typical", lang, m=m)
        if a.explanation:
            line += "; " + tr("ev_why", lang, x=a.explanation[:120])
        ev.append(line)
    for r in s.get("retries", []):
        ev.append(tr("ev_retry", lang, q=r["question_id"], opt=r["option"], res=res(r["correct"])))
    o = s.get("outcome", {"reconstruct": [], "transfers": []})
    for r in o["reconstruct"]:
        line = tr("ev_recon", lang, item=r["item"], step=r["step"], res=res(r["found"]))
        if r.get("rubric"):
            line += "; " + tr("ev_rubric", lang, v=tr(f"verdict_{r['rubric']['verdict']}", lang))
        ev.append(line)
    for x in o["transfers"]:
        ev.append(tr("ev_transfer", lang, q=x["question_id"], opt=x["option"], res=res(x["correct"])))
    sure = [a for a in s["asked"] if a.confidence == "sure"]
    unsure = [a for a in s["asked"] if a.confidence == "unsure"]
    kw = tutor.style_kwargs(s["profile"], lang)
    note = _handoff_text(s, lang, names)
    return SessionSummary(
        session_id=session_id, diagnosis=HypProb(id=h, name_en=names[h], prob=round(float(d.as_dict()[h]), 6)),
        diagnosis_names=MisconceptionView(**mv), status=status, evidence=ev,
        tried=list(s.get("states", ["DIAGNOSE"])),
        outcome=safetext.static(tr(f"outcome_{status}", lang), lang=lang, style_kwargs=kw),
        next_step=safetext.static(tr(f"next_{status}", lang), lang=lang, style_kwargs=kw),
        lesson_refs=_lesson_refs(mv),
        handoff_note=safetext.static(note, lang=lang, style_kwargs={**kw, "max_words_per_sentence": 40})
        if note else None,
        calibration=Calibration(sure_correct=sum(a.correct for a in sure), sure_total=len(sure),
                                unsure_correct=sum(a.correct for a in unsure), unsure_total=len(unsure)),
        cost=_cost(session_id)).model_dump()


def report(session_id: str, lang: str | None = None) -> dict:
    """The one-page teacher / parent report as Markdown + PDF (FR / AR / EN), with the calibration chart.
    Built by code from summary(); no LLM."""
    from engine.studio import export_dir, rel
    from engine.studio.pdf import Doc
    s = _SESSIONS[session_id]
    lang = lang_of(lang or _lang(s))
    r = summary(session_id, lang)
    out = export_dir(session_id)
    name_key = {"fr": "name_fr", "ar": "name_ar"}.get(lang, "name_en")
    mname = r["diagnosis_names"].get(name_key) or r["diagnosis_names"]["name_en"]
    c = r["calibration"]
    chart = _calibration_chart(c, out / "calibration.png", lang)
    sections = [
        (tr("rep_title", lang), None),
        (f"{tr('rep_student', lang)}: {s['student'].get('name', '')} ({s['student'].get('level', '')})", "p"),
        (tr("rep_found", lang), "h"), (f"{mname} ({tr('rep_prob', lang)} {r['diagnosis']['prob']:.2f})", "p"),
        (tr("rep_evidence", lang), "h"), *[(f"- {e}", "p") for e in r["evidence"]],
        (tr("rep_tried", lang), "h"), (" -> ".join(tr(f"state_{x}", lang) for x in r["tried"]), "p"),
        (tr("rep_outcome", lang), "h"), (r["outcome"]["text"], "p"),
        (tr("rep_next", lang), "h"), (r["next_step"]["text"], "p"),
    ]
    if r["lesson_refs"]:
        sections += [(tr("rep_lesson", lang), "h")] + [
            (f"- {x['file']}, p. {x['page']}" + (f" ({x['source_url']})" if x.get("source_url") else ""), "p")
            for x in r["lesson_refs"]]
    if r["handoff_note"]:
        sections += [(tr("rep_handoff", lang), "h"), (r["handoff_note"]["text"], "p")]
    sections += [(tr("rep_calibration", lang), "h"),
                 (tr("rep_cal_line", lang, a=c["sure_correct"], b=c["sure_total"], c=c["unsure_correct"],
                     d=c["unsure_total"]), "p"), ("[chart]", "img"), (tr("rep_footer", lang), "p")]
    md = []
    for text, kind in sections:
        md.append(f"# {text}" if kind is None else f"## {text}" if kind == "h" else
                  f"![calibration](calibration.png)" if kind == "img" else text)
    mdp = out / f"report_{lang}.md"
    mdp.write_text("\n\n".join(md), encoding="utf-8")
    doc = Doc(tr("rep_title", lang))
    for text, kind in sections:
        if kind is None:
            doc.title(text)
        elif kind == "h":
            doc.heading(text)
        elif kind == "img":
            doc.image(chart, w=110)
        else:
            doc.text(text, size=10, gap=1)
    pdf = doc.save(out / f"report_{lang}.pdf")
    return ReportExport(session_id=session_id, lang=lang,
                        files=[OutputFile(path=rel(mdp), mime="text/markdown"),
                               OutputFile(path=rel(pdf), mime="application/pdf"),
                               OutputFile(path=rel(chart), mime="image/png")]).model_dump()


def _calibration_chart(c: dict, path, lang: str):
    """Bar chart: share of right answers when the student said 'sure' vs 'not sure' (counts on the bars)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = ["sure", "not sure"] if lang == "ar" else [tr("conf_sure", lang), tr("conf_unsure", lang)]
    tot = [c["sure_total"], c["unsure_total"]]
    ok = [c["sure_correct"], c["unsure_correct"]]
    share = [o / n if n else 0 for o, n in zip(ok, tot)]
    fig, ax = plt.subplots(figsize=(4.5, 2.6), dpi=150)
    bars = ax.bar(labels, share, color=["#0f766e", "#94a3b8"], width=0.5)
    for b, o, n in zip(bars, ok, tot):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.03, f"{o}/{n}", ha="center", fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0%", "50%", "100%"])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


# ---------------------------------------------------------------- course folders (step 11, no LLM)
def course_index(refresh: bool = False) -> dict:
    """(Re)index data/courses/ (PDF/TXT). Returns the indexing report (files, chunks, unreadable pages, flags)."""
    from engine import rag
    return copy.deepcopy(rag.index(refresh=refresh).report)


def _retrieval_label(ix) -> str:
    return "BM25 + " + ix.report["embeddings"] + " (reciprocal rank fusion)" if ix.emb is not None else \
        "BM25 only (" + str(ix.report["embeddings"]) + ")"


def course_search(query: str, k: int = 3) -> dict:
    """Course Q&A, extractive: the most relevant passages with file + page. No LLM (paused: token budget)."""
    from engine import rag
    query = (query or "").strip()
    if not query:
        raise ValueError("empty query")
    ix = rag.index()
    hits = [h for h in ix.search(query, k) if h["relevant"]]
    found = bool(hits)
    if not ix.chunks:
        note = "No course files are indexed. Add PDF files to data/courses/<folder>/ and re-index."
    elif not found:
        note = "Nothing relevant was found in your course files. TRACE does not answer from memory."
    else:
        note = "Passages copied from your course files (not rewritten). Check the page cited."
    return CourseAnswer(query=query, found=found, note=note, retrieval=_retrieval_label(ix),
                        hits=[CourseHit(folder=h["folder"], file=h["file"], page=h["page"],
                                        snippet=rag.snippet(h["text"], query), lang=h["lang"],
                                        source_url=h["source_url"], allow_derivatives=h["allow_derivatives"],
                                        score=h["score"]) for h in hits]).model_dump()


def ask(question: str, lang: str = "fr", session_id: str | None = None) -> dict:
    """Course chat: school questions answered from the course files with citations; anything else refused."""
    from engine import chat, style
    s = _SESSIONS.get(session_id) if session_id else None
    lang = lang_of(_lang(s) if s and not lang else lang)
    kw = tutor.style_kwargs(s["profile"] if s else {}, lang)
    suspects = {}
    if s:
        names = _names()
        suspects = {h: names[h] for h, p in s["diag"].as_dict().items() if h != "M0" and p > 0.2}
    return chat.answer(question, lang, kw, suspects)


def study_plan(files: list[tuple[str, bytes]], details: str = "", lang: str = "fr",
               session_id: str | None = None) -> dict:
    """Study plan from uploaded PDF / TXT / MD files (saved to data/courses/uploads/). Targets the diagnosis if any."""
    from engine import study_plan as sp
    s = _SESSIONS.get(session_id) if session_id else None
    lang = lang_of(lang)
    kw = tutor.style_kwargs(s["profile"] if s else {}, lang)
    h = _diagnosed(s) if s else None
    mv = next((m for m in misconceptions() if m["id"] == h), None) if h else None
    names = _names()
    suspects = {k: names[k] for k, p in s["diag"].as_dict().items() if k != "M0" and p > 0.2} if s else {}
    return sp.make(files, details or "", lang, kw, suspects, mv, _mis(h) if h else None)


def _practice_ctx(session_id: str | None, lang: str):
    s = _SESSIONS.get(session_id) if session_id else None
    kw = tutor.style_kwargs(s["profile"] if s else {}, lang_of(lang))
    names = _names()
    suspects = {k: names[k] for k, p in s["diag"].as_dict().items() if k != "M0" and p > 0.2} if s else {}
    return kw, suspects


def practice_quiz(files: list[tuple[str, bytes]] | None = None, text: str = "", source: str = "file",
                  details: str = "", lang: str = "fr", session_id: str | None = None) -> dict:
    """Practice quiz from the student's file or pasted text (key cross-checked, kept on the server)."""
    from engine import practice
    kw, suspects = _practice_ctx(session_id, lang)
    return practice.make_quiz(files or [], text, source, details, lang, kw, suspects)


def practice_check(quiz_id: str, question_id: str, option: str) -> dict:
    from engine import practice
    return practice.check(quiz_id, question_id, option)


def practice_cards(files: list[tuple[str, bytes]] | None = None, text: str = "", source: str = "file",
                   details: str = "", lang: str = "fr", session_id: str | None = None) -> dict:
    """Flashcards from the student's file or pasted text (guarded drafts)."""
    from engine import practice
    kw, suspects = _practice_ctx(session_id, lang)
    return practice.make_cards(files or [], text, source, details, lang, kw, suspects)


def practice_summary(files: list[tuple[str, bytes]] | None = None, text: str = "", source: str = "file",
                     focus: str = "", pages: int = 2, lang: str = "fr", session_id: str | None = None) -> dict:
    """Summary of the student's file or pasted text; every bullet cites its page (guarded)."""
    from engine import practice
    kw, suspects = _practice_ctx(session_id, lang)
    return practice.make_summary(files or [], text, source, focus, pages, lang, kw, suspects)


def _lesson_refs(mv: dict, k: int = 2) -> list[LessonRef]:
    """Curriculum-grounded remediation: lesson pages for the diagnosed misconception (only if courses exist)."""
    if mv["id"] == "M0":
        return []
    try:
        from engine import rag
        if not any(p.suffix.lower() in rag.TEXT_EXT for p in rag.COURSES.rglob("*")
                   if p.name not in ("SOURCES.md", "README.md")):
            return []
        m = _mis(mv["id"]) or {}
        query = " ".join(x for x in (mv.get("name_fr"), mv.get("name_en"), m.get("description")) if x)
        return [LessonRef(file=h["file"], page=h["page"], snippet=rag.snippet(h["text"], query, 200),
                          source_url=h["source_url"]) for h in rag.index().search(query, k) if h["relevant"]]
    except Exception:  # noqa: BLE001  retrieval must never break the report
        return []


# ---------------------------------------------------------------- simulations (step 13, no LLM)
def _phys(s: dict):
    """The session's physics posterior (separate from the maths one; same Bayesian engine)."""
    from engine.sims import poe
    if "phys" not in s:
        its = poe.live_items(cfg().get("live", {}).get("allow_unverified_dev", False))
        s["phys"] = {"items": {i["id"]: i for i in its}, "diag": bayes.Diagnoser(poe.table(its)), "log": []}
    return s["phys"]


def _phys_posterior(ph) -> list[HypProb]:
    from engine.sims import poe
    names = {m["id"]: m["name_en"] for m in poe.misconceptions()}
    return [HypProb(id=h, name_en=names[h], prob=round(p, 6)) for h, p in ph["diag"].as_dict().items()]


def _sim_view(it: dict, lang: str) -> SimItemView:
    return SimItemView(id=it["id"], template=it["template"], text=it["text"].get(lang) or it["text"]["en"],
                       options={k: o["text"].get(lang) or o["text"]["en"] for k, o in it["options"].items()},
                       runs_params=it["runs"], transfer_of=it.get("transfer_of"))


def sim_templates() -> dict:
    """Parameter schemas (ranges + units) of the whitelisted templates, for sliders."""
    from engine import sims
    return sims.schemas()


def sim_run(template: str, params: dict) -> dict:
    """Free exploration (Observe with sliders). Out-of-range parameters raise ValueError (schema)."""
    from pydantic import ValidationError

    from engine import sims
    try:
        r = sims.run(template, params)
    except ValidationError as e:
        raise ValueError(str(e)) from None
    return SimRun(label="a", **r).model_dump()


def sim_items(session_id: str) -> list[dict]:
    s = _SESSIONS[session_id]
    return [_sim_view(i, _lang(s)).model_dump() for i in _phys(s)["items"].values() if not i.get("transfer_of")]


def _sim_result_text(it: dict, runs: dict, lang: str):
    k = it["kind"]
    if k == "compare_landing":
        txt = tr("sim_res_landing", lang, a=runs["a"]["result"]["time_to_ground_s"], b=runs["b"]["result"]["time_to_ground_s"])
    elif k == "compare_period":
        txt = tr("sim_res_period", lang, a=runs["a"]["result"]["period_s"], b=runs["b"]["result"]["period_s"])
    elif k == "during_push":
        txt = tr("sim_res_push", lang, v=runs["a"]["result"]["speed_end_of_push_m_s"])
    else:
        txt = tr("sim_res_after", lang, v=runs["a"]["result"]["speed_at_end_m_s"])
    return safetext.static(txt, lang=lang)


def sim_predict(session_id: str, item_id: str, option: str, confidence: str | None) -> dict:
    """Predict -> Observe: grade the prediction against the computed simulation; update the physics posterior."""
    from engine.sims import poe
    s = _SESSIONS[session_id]
    ph = _phys(s)
    it = ph["items"][item_id]
    if option not in it["options"]:
        raise ValueError(f"unknown option {option!r}")
    if confidence not in ("sure", "unsure"):
        raise ValueError("confidence tap is required: 'sure' or 'unsure'")
    lang = _lang(s)
    runs = poe.runs(it)
    correct = option == it["correct"]
    ph["diag"].observe_answer(item_id, option, confidence)
    ph["log"].append({"item": item_id, "option": option, "confidence": confidence, "correct": correct})
    is_transfer = bool(it.get("transfer_of"))
    nxt = None
    if is_transfer:
        stage, expects, msg = "transfer_result", "none", tutor.txt(s, "sim_done")
    else:
        stage, expects, msg = "observe", "explanation", safetext.static(
            tr("sim_observe", lang) + " " + tr("sim_explain_prompt", lang), lang=lang)
    return SimTurn(item_id=item_id, stage=stage, observed=it["observed"],
                   grading=Grading(correct=correct, method="simulation", label=tr("grade_simulation", lang)),
                   result_text=_sim_result_text(it, runs, lang),
                   runs=[SimRun(label=k, **v) for k, v in runs.items()], posterior=_phys_posterior(ph),
                   message=msg, expects=expects, next_item=nxt).model_dump()


def sim_explain(session_id: str, item_id: str, text: str | None = None) -> dict:
    """Explain: stored for the teacher (no LLM grading), then the transfer prediction."""
    s = _SESSIONS[session_id]
    ph = _phys(s)
    it = ph["items"][item_id]
    lang = _lang(s)
    ph["log"].append({"item": item_id, "explanation": (text or "")[:500]})
    nxt_id = it.get("transfer")
    nxt = _sim_view(ph["items"][nxt_id], lang) if nxt_id in ph["items"] else None
    return SimTurn(item_id=item_id, stage="explain_saved", observed=it["observed"],
                   grading=Grading(correct=None, method="none", label=""), posterior=_phys_posterior(ph),
                   message=tutor.txt(s, "sim_transfer" if nxt else "sim_done"),
                   expects="transfer_answer" if nxt else "none", next_item=nxt).model_dump()


# ---------------------------------------------------------------- game "Chasse aux erreurs" (step 14, no LLM)
def _game_turn(s: dict, feedback: dict | None, lead: str = "") -> dict:
    from engine import game
    g = s["game"]
    lang = _lang(s)
    view = game.round_view(g, _bank(), lang)
    done = view is None
    if done:
        text = tr("game_over", lang, points=g["points"])
    else:
        text = tr("game_start", lang)
    text = (lead + " " if lead else "") + text
    fb = None
    if feedback:
        names = game._names(_bank(), lang)
        fb = GameFeedback(step_ok=feedback["step_ok"], reason_ok=feedback["reason_ok"],
                          correct_step=feedback["correct_step"], correct_reason=names[feedback["correct_reason"]],
                          points_gained=feedback["points_gained"])
    return GameTurn(round=GameRoundView(**view) if view else None, feedback=fb, points=g["points"],
                    streak=g["streak"], best_streak=g["best_streak"], done=done,
                    message=safetext.static(text, lang=lang, style_kwargs=tutor.style_kwargs(s["profile"], lang)),
                    posterior=_posterior(s["diag"])).model_dump()


def game_start(session_id: str) -> dict:
    """New game: 5 rounds from the verified worked solutions (the diagnosed misconception first)."""
    from engine import game
    s = _SESSIONS[session_id]
    first = s.get("target") if s.get("target") not in (None, "M0") else None
    s["game"] = game.new_game(_bank(), first)
    if not s["game"]["rounds"]:
        raise ValueError("no verified worked solutions in the bank")
    return _game_turn(s, None)


def game_answer(session_id: str, step: int, reason: str) -> dict:
    from engine import game
    s = _SESSIONS[session_id]
    g = s.get("game")
    if not g or g["i"] >= len(g["rounds"]):
        raise ValueError("no game round is open: call game_start")
    fb = game.answer(g, int(step), reason, s["diag"])
    lang = _lang(s)
    if fb["step_ok"] and fb["reason_ok"]:
        lead = tr("game_right", lang)
    else:
        lead = tr("game_partly", lang, step=fb["correct_step"], reason=game._names(_bank(), lang)[fb["correct_reason"]])
    return _game_turn(s, fb, lead)


def _diagnosed(s: dict) -> str | None:
    """The misconception to target: the tutor's target, else the top hypothesis if it is a misconception
    above 0.5. None = no diagnosis yet."""
    if s.get("target") and s["target"] != "M0":
        return s["target"]
    h, p = s["diag"].top()
    return h if h != "M0" and p >= 0.5 else None


def studio_generate(session_id: str, tool: str, source: dict | None = None) -> dict:
    """Study Studio (step 12). `source` = {"kind": "diagnosis"} (default) | {"kind": "folder", "folder": name} |
    {"kind": "pages", "pages": [{"file", "page"}]}. Targets the diagnosed misconception first."""
    from engine.studio import TOOLS, tools
    if tool not in TOOLS:
        raise NotImplementedError(f"Study Studio tool {tool!r} is not built (built: {', '.join(TOOLS)})")
    s = _SESSIONS[session_id]
    lang = _lang(s)
    h = _diagnosed(s)
    mv = next((m for m in misconceptions() if m["id"] == h), None) if h else None
    names = _names()
    post = s["diag"].as_dict()
    thr = cfg().get("guards", {}).get("congruency_threshold", 0.2)
    suspects = {k: names[k] for k, p in post.items() if k != "M0" and (p > thr or k == h)}
    return tools.generate(s, session_id, tool, source or {"kind": "diagnosis"}, mv, _mis(h) if h else None, lang,
                          tutor.style_kwargs(s["profile"], lang), _bank(), suspects)


def studio_cards(session_id: str, verified_only: bool = False) -> list[dict]:
    """Drafted flashcards (review screen: verified_only=False) or the deck (verified_only=True)."""
    from engine.studio import flashcards
    return flashcards.rows(session_id, verified_only)


def studio_card_verify(card_id: str, ok: bool) -> dict:
    """Human review of a drafted card: ok=True approves it, ok=False deletes it."""
    from engine.studio import flashcards
    flashcards.verify(card_id, ok)
    return {"id": card_id, "verified": bool(ok), "deleted": not ok}


def studio_card_review(session_id: str, card_id: str, rating: str) -> dict:
    """Leitner review (again / hard / good / easy). A lapse on a misconception card is evidence for it."""
    from engine.studio import flashcards
    s = _SESSIONS[session_id]
    r = flashcards.review(card_id, rating)
    if r["lapse"] and r["misconception"] in bayes.H and r["misconception"] != "M0":
        import numpy as np
        lik = np.ones(len(bayes.H))
        lik[bayes.H.index(r["misconception"])] = 1.5
        s["diag"].update_lik(lik ** s["diag"].p["tau"], "flashcard_lapse", {"card": card_id})
    return {**r, "posterior": [p.model_dump() for p in _posterior(s["diag"])]}


def list_results() -> list[str]:
    return sorted(p.stem for p in (ROOT / "results").glob("*.json"))


def read_results(name: str) -> dict:
    """Read-only access to results/<name>.json (returns a deep copy; the frontend never writes results)."""
    if not _RESULTS_NAME.match(name):
        raise ValueError("bad results name")
    p = ROOT / "results" / f"{name}.json"
    return copy.deepcopy(json.loads(p.read_text(encoding="utf-8")))
