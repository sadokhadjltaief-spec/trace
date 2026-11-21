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
                             SessionState, SessionSummary, SimItemView, SimRun, SimTurn, TutorTurn)

_SESSIONS: dict[str, dict] = {}
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
    llm.set_demo_mode(demo)
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
    grading = Grading(correct=correct, method="answer_key", label="Checked against the answer key")
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




def summary(session_id: str) -> dict:
    """One-page report data, built by code from the session (no LLM text). Lesson references need RAG (P1)."""
    s = _SESSIONS[session_id]
    d: bayes.Diagnoser = s["diag"]
    names = _names()
    h = s.get("target") or d.top()[0]
    h = h if h in names else d.top()[0]
    mv = next(m for m in misconceptions() if m["id"] == h)
    status = tutor.mastery_status(s) if "outcome" in s else "in_progress"
    by_id = s["by_id"]
    ev = []
    for a in s["asked"]:
        q = by_id[a.question_id]
        line = f"{a.question_id}: chose {a.option} ({a.confidence}), {'correct' if a.correct else 'wrong'}"
        m = q.get("option_misconception", {}).get(a.option)
        if m:
            line += f"; this option is typical of {m}"
        if a.explanation:
            line += f"; explanation: '{a.explanation[:120]}'"
        ev.append(line)
    for r in s.get("retries", []):
        ev.append(f"{r['state']} retry on {r['question_id']}: {r['option']} "
                  f"({'correct' if r['correct'] else 'wrong'})")
    o = s.get("outcome", {"reconstruct": [], "transfers": []})
    for r in o["reconstruct"]:
        line = f"Find-the-mistake {r['item']}: chose step {r['step']} ({'right' if r['found'] else 'not the wrong step'})"
        if r.get("rubric"):
            line += f"; explanation graded by the LLM: {r['rubric']['verdict']}"
        ev.append(line)
    for x in o["transfers"]:
        ev.append(f"New question {x['question_id']}: {x['option']} ({'correct' if x['correct'] else 'wrong'})")
    sure = [a for a in s["asked"] if a.confidence == "sure"]
    unsure = [a for a in s["asked"] if a.confidence == "unsure"]
    lang = _lang(s)
    kw = tutor.style_kwargs(s["profile"], lang)
    note = s.get("handoff_note")
    return SessionSummary(
        session_id=session_id, diagnosis=HypProb(id=h, name_en=names[h], prob=round(float(d.as_dict()[h]), 6)),
        diagnosis_names=MisconceptionView(**mv), status=status, evidence=ev,
        tried=list(s.get("states", ["DIAGNOSE"])),
        outcome=safetext.static(tr(f"outcome_{status}", lang), lang=lang, style_kwargs=kw),
        next_step=safetext.static(tr(f"next_{status}", lang), lang=lang, style_kwargs=kw),
        lesson_refs=_lesson_refs(mv),
        handoff_note=safetext.static(note, style_kwargs=kw) if note else None,
        calibration=Calibration(sure_correct=sum(a.correct for a in sure), sure_total=len(sure),
                                unsure_correct=sum(a.correct for a in unsure), unsure_total=len(unsure)),
        cost=_cost(session_id)).model_dump()


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


def studio_generate(session_id: str, tool: str, source: dict) -> dict:
    raise NotImplementedError("Study Studio arrives in P1 step 12 (use engine.api_fake)")


def list_results() -> list[str]:
    return sorted(p.stem for p in (ROOT / "results").glob("*.json"))


def read_results(name: str) -> dict:
    """Read-only access to results/<name>.json (returns a deep copy; the frontend never writes results)."""
    if not _RESULTS_NAME.match(name):
        raise ValueError("bad results name")
    p = ROOT / "results" / f"{name}.json"
    return copy.deepcopy(json.loads(p.read_text(encoding="utf-8")))
