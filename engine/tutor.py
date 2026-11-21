"""Tutor state machine. Code decides the state and the message type; the LLM only writes the wording.

DIAGNOSE -> HINT_1 -> HINT_2 -> HINT_3 -> RECONSTRUCT -> TRANSFER -> DONE
  the student retries the repair question after each hint; a correct retry skips to RECONSTRUCT
  M0 diagnosed -> TRANSFER directly (mastery check)
RECONSTRUCT: the student names the wrong step (deterministic) and says why (LLM rubric, labelled in the UI).
TRANSFER (fresh question, answer key, also Bayes evidence): correct -> DONE; failed -> HINT_1 on that question
for the same misconception (max 2 loops); still failing -> HANDOFF with a 3-line note built by code.

Each hint turn = two LLM calls: (1) a structured diagnosis of the student's error (error, faulty step) for the
misconception chosen by bayes.py, (2) the message of the allowed type. Then the guards (engine/guards.py).
On a guard failure: regenerate once with the failure as feedback, then fall back to the human-verified bank hint
of the same level, then to a fixed template. Retries are graded against the answer key; they do not update the
posterior (the same question re-answered after a hint is not independent evidence).
"""
from __future__ import annotations

from engine import guards, llm, mathcheck as mc, safetext, style
from engine import i18n
from engine.i18n import lang_of, t as tr
from engine.contract import Agenda, Check, Grading, QuestionView, Reconstruction, SafeText

LANG = {"fr": "French", "ar": "Modern Standard Arabic", "en": "English"}
HINT_TYPES = {
    1: "Level 1: ONE short question that points the student at the faulty step. Do not explain the rule yet.",
    2: "Level 2: a contrasting example. Use a simpler case with DIFFERENT numbers from the question, where the "
       "wrong idea visibly gives a wrong result and the correct idea gives a sensible one. Then ask the student "
       "to look at their question again.",
    3: "Level 3: a near-complete scaffold for THIS question: list the steps, do the setup, and stop before the "
       "final calculation. Never state the final answer or the correct option.",
}
REPAIR_STEPS = ["HINT_1", "HINT_2", "HINT_3", "RECONSTRUCT", "TRANSFER"]

DIAG_SYS = """You analyse one student's wrong answer to a maths question. The misconception has already been
identified by a separate statistical engine; do not change it. Describe the error precisely.
Return JSON: {"error": "what the student did, in one sentence", "faulty_step": "the exact step that went wrong",
"correct_idea": "the idea the student is missing, without the final answer"}"""

HINT_SYS = """You are a calm, precise maths tutor writing ONE hint for a student who will retry the question.
Rules:
- Write ONLY in {lang}{script}. Maths as plain text with digits (1/3, 2 x 5, -7), no LaTeX.
- Never give the final answer, the correct option letter, or a number equal to the answer.
- Never state or use the student's wrong idea as if it were correct.
- Any equality you write must be true.
- At most {max_words} words per sentence, at most {max_q} question mark(s), no exclamation marks, no emoji,
  no ALL-CAPS words, no praise words.
- Under 60 words in total.{profile_rules}
Message type you must write: {hint_type}
Return JSON: {{"message": "..."}}"""


def _plain_q(q: dict) -> str:
    opts = "; ".join(f"{k}: {mc.latex_to_plain(v)}" for k, v in q["options"].items())
    return f"{mc.latex_to_plain(q['text'])} Options: {opts}"


def style_kwargs(profile: dict, lang: str = "en") -> dict:
    """Active style-linter limits for this student's support profile (engine/style.py, profiles.yaml)."""
    return style.lint_kwargs(profile, lang)


def _lang(s: dict) -> str:
    return lang_of(s.get("student", {}).get("lang"))


def txt(s: dict, key: str, **kw):
    """A fixed string (i18n/tutor.json) in the student's language, through the style linter."""
    lang = _lang(s)
    return safetext.static(tr(key, lang, **kw), lang=lang, style_kwargs=style_kwargs(s.get("profile", {}), lang))


def frame(s: dict, f: dict) -> dict:
    """fixed_template toggle: every turn uses the same layout, built by code around the checked message:
    Situation: <message> / Your task: <what to do, from `expects`> / What happens next: <agenda.next>.
    The leak/congruency/math results of the inner message are kept; the style linter re-runs on the framed text."""
    if not style.resolve(s.get("profile")).get("fixed_template") or "message" not in f:
        return f
    lang = _lang(s)
    m = f["message"]
    if not m.shown_allowed:
        return f
    task = tr(f"task_{f['expects']}", lang)
    text = (f"{tr('frame_situation', lang)}: {m.text}\n{tr('frame_task', lang)}: {task}\n"
            f"{tr('frame_next', lang)}: {f['agenda'].next}.")
    viol = style.lint(text, **style_kwargs(s.get("profile"), lang))
    checks = [c for c in m.checks if c.name != "style"] + [
        Check(name="style", status="fail" if viol else "pass", detail="; ".join(viol) or "framed (fixed_template)")]
    ok = not any(c.status == "fail" for c in checks)
    framed = SafeText(text=text, lang=m.lang, origin=m.origin, checks=checks, shown_allowed=ok,
                      fallback_used=m.fallback_used)
    return {**f, "message": framed if ok else m}


def agenda(state: str, lang: str = "en") -> Agenda:
    i = REPAIR_STEPS.index(state) if state in REPAIR_STEPS else len(REPAIR_STEPS) - 1
    key = {"HINT_1": "agenda_retry", "HINT_2": "agenda_retry", "HINT_3": "agenda_retry",
           "RECONSTRUCT": "agenda_recon", "TRANSFER": "agenda_transfer"}.get(state, "agenda_results")
    return Agenda(step=i + 1, total=len(REPAIR_STEPS), next=tr(key, lang))


def pick_repair_question(s: dict, h: str) -> str:
    """The question the student retries: the last one answered with an option that maps to h; else the last
    wrong one; else an unasked question for h."""
    by_id = s["by_id"]
    for a in reversed(s["asked"]):
        q = by_id[a.question_id]
        if q.get("option_misconception", {}).get(a.option) == h:
            return a.question_id
    for a in reversed(s["asked"]):
        if not a.correct:
            return a.question_id
    asked = {a.question_id for a in s["asked"]}
    for qid in s["pool"]:
        if by_id[qid].get("target") == h and qid not in asked:
            return qid
    return s["asked"][-1].question_id if s["asked"] else s["pool"][0]


def pick_transfer_question(s: dict, h: str) -> str | None:
    asked = {a.question_id for a in s["asked"]} | set(s.get("repair_done", []))
    pool = [qid for qid in s["pool"] if qid not in asked]
    if h in (None, "M0"):  # mastery check: any unused question
        return (pool or [None])[0]
    same = [qid for qid in pool if s["by_id"][qid].get("target") == h]  # transfer = same misconception only
    return (same or [None])[0]


# ---------------------------------------------------------------- LLM steps
def diagnose_error(q: dict, option: str, explanation: str | None, mis: dict) -> dict:
    user = (f"Question: {_plain_q(q)}\nStudent chose: {option}: {mc.latex_to_plain(q['options'][option])}\n"
            f"Student explanation: {explanation or '(none)'}\n"
            f"Misconception identified by the engine: {mis['name_en']} - {mis.get('description', '')}")
    return llm.ask_json(DIAG_SYS, user, purpose="tutor_diagnosis", max_tokens=1024) or {}


def write_hint(level: int, q: dict, diag: dict, mis: dict, lang: str, kw: dict, feedback: str = "",
               attempt: int = 0, profile: dict | None = None) -> str:
    script = {"ar": " (Arabic script; keep the numbers as digits)",
              "fr": " (address the student as \"tu\", never \"vous\")"}.get(lang, "")
    sysmsg = HINT_SYS.format(lang=LANG.get(lang, "English"), script=script, max_words=kw["max_words_per_sentence"],
                             max_q=kw["max_questions"], hint_type=HINT_TYPES[level],
                             profile_rules=style.prompt_rules(profile or {}))
    user = (f"Question: {_plain_q(q)}\nCorrect option (NEVER reveal): {q['correct']}\n"
            f"Student's misconception: {mis['name_en']}\nDiagnosis of the error: "
            f"{diag.get('error', '')} Faulty step: {diag.get('faulty_step', '')} "
            f"Missing idea: {diag.get('correct_idea', '')}")
    if feedback:
        user += f"\nYour previous draft was rejected by a checker: {feedback}\nWrite a new hint that fixes this."
    d = llm.ask_json(sysmsg, user, purpose=f"tutor_hint_{level}", max_tokens=1024,
                     seed_tag="" if attempt == 0 else f"regen{attempt}")
    return str((d or {}).get("message", "")).strip()


def hint_message(s: dict, level: int, h: str, names: dict, mis: dict, posterior: dict) -> tuple:
    """Returns (SafeText, guard_events, detail). Never raises: LLM failure -> verified fallback."""
    q = s["by_id"][s["repair_q"]]
    lang = lang_of(s["student"].get("lang", "en"))
    kw = style_kwargs(s["profile"], lang)
    events, detail = [], {"level": level}
    last = s["last_choice"]
    try:
        if "error_diag" not in s:
            s["error_diag"] = diagnose_error(q, last["option"], last.get("explanation"), mis)
        diag = s["error_diag"]
        feedback = ""
        for attempt in range(2):  # first draft + one regeneration
            text = write_hint(level, q, diag, mis, lang, kw, feedback, attempt, profile=s["profile"])
            if not text:
                feedback = "empty message"
                continue
            checks, gd = guards.check(text, q, posterior, names, style_kwargs=kw, lang=lang)
            detail[f"attempt{attempt}"] = {"text": text, "checks": [c.model_dump() for c in checks]}
            failed = [c for c in checks if c.status == "fail"]
            if not failed:
                events += guards.events(checks, "shown")
                return safetext.from_guards(text, checks, lang=lang), events, detail
            events += guards.events(checks, "regenerated" if attempt == 0 else "fallback")
            feedback = "; ".join(f"{c.name}: {c.detail}" for c in failed)[:400]
    except Exception as e:  # noqa: BLE001  (CacheMiss in demo mode, API failure)
        detail["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    fb, fb_events = fallback(q, level, kw, lang, posterior, names)
    return fb, events + fb_events, detail


TRANSLATE_HINT_SYS = """Translate this maths hint for a school student into {lang}{script}. Keep every number and
operation exactly; maths as plain text with digits. Do not add anything. Return JSON: {{"text": "..."}}"""


def fallback(q: dict, level: int, kw: dict, lang: str = "en", posterior: dict | None = None,
             names: dict | None = None) -> tuple:
    """Verified bank hint of the same level (English). For fr/ar it is translated by the LLM and the translation
    goes through all four guards; if that fails, a fixed template in the student's language."""
    hints = q.get("verified_hints") or []
    events = []
    if q.get("verified") and len(hints) >= level:
        if lang == "en":
            t = safetext.static(hints[level - 1], origin="verified_bank", style_kwargs=kw, fallback_used=True)
            if t.shown_allowed:
                return t, events
        else:
            try:
                script = {"ar": " (Arabic script)", "fr": " (address the student as \"tu\")"}.get(lang, "")
                d = llm.ask_json(TRANSLATE_HINT_SYS.format(lang=LANG[lang], script=script), hints[level - 1],
                                 purpose="tutor_fallback_translate", max_tokens=512)
                text = str((d or {}).get("text", "")).strip()
                if text:
                    checks, _ = guards.check(text, q, posterior or {}, names or {}, style_kwargs=kw, lang=lang)
                    ok = not any(c.status == "fail" for c in checks)
                    events += guards.events(checks, "shown" if ok else "fallback")
                    if ok:
                        return safetext.from_guards(text, checks, lang=lang, fallback_used=True), events
            except Exception:  # noqa: BLE001
                pass
    lang = lang_of(lang)  # last resort: fixed text in the student's language (i18n/tutor.json)
    return safetext.static(tr("last_resort", lang), lang=lang, style_kwargs=kw, fallback_used=True), events


# ---------------------------------------------------------------- transitions
def qview(q: dict, lang: str = "en") -> QuestionView:
    text, options = i18n.question(q, lang)
    return QuestionView(id=q["id"], text=text, options=options, requires_confidence=False)


def begin(s: dict, h: str, names: dict, mis: dict | None, posterior: dict) -> dict:
    """Called when the diagnosis stops. Returns TutorTurn fields (state, message, expects, question, ...)."""
    s.setdefault("outcome", {"reconstruct": [], "transfers": [], "status": "in_progress"})
    s.setdefault("loops", 0)
    s["names"] = names
    if h == "M0" or mis is None:
        s["target"] = "M0"
        return enter_transfer(s, h)
    s["repair_q"] = pick_repair_question(s, h)
    rec = next(a for a in reversed(s["asked"]) if a.question_id == s["repair_q"]) \
        if any(a.question_id == s["repair_q"] for a in s["asked"]) else None
    s["last_choice"] = {"option": rec.option if rec else "", "explanation": rec.explanation if rec else None}
    if not rec:  # nothing answered for h: present the question first, no hint yet
        s["last_choice"] = None
    s["target"] = h
    return enter_hint(s, 1, names, mis, posterior)


def enter_hint(s: dict, level: int, names: dict, mis: dict, posterior: dict) -> dict:
    s["state"] = f"HINT_{level}"
    q = s["by_id"][s["repair_q"]]
    if s.get("last_choice") is None or not s["last_choice"].get("option"):
        msg = txt(s, "answer_first")
        events, detail = [], {}
    else:
        msg, events, detail = hint_message(s, level, s["target"], names, mis, posterior)
    s.setdefault("tutor_log", []).append({"state": s["state"], "detail": detail})
    return {"state": s["state"], "message": msg, "expects": "retry", "agenda": agenda(s["state"], _lang(s)),
            "question": qview(q, _lang(s)), "guard_events": events}


def enter_reconstruct(s: dict, bank: dict) -> dict:
    s["state"] = "RECONSTRUCT"
    s.setdefault("repair_done", []).append(s["repair_q"])
    used = s.setdefault("recon_used", [])
    items = [r for r in bank.get("reconstruction", [])
             if r["misconception"] == s["target"] and r.get("verified") and r["id"] not in used]
    if not items:  # no (unused) verified item for this misconception
        return enter_transfer(s, s["target"])
    r = items[0]
    used.append(r["id"])
    s["recon"] = r
    s["recon_attempts"] = 0
    return {"state": "RECONSTRUCT", "expects": "error_step", "agenda": agenda("RECONSTRUCT", _lang(s)),
            "message": txt(s, "recon_intro"), "reconstruction": recon_view(r, _lang(s)), "guard_events": []}


def recon_view(r: dict, lang: str = "en") -> Reconstruction:
    problem, steps = i18n.reconstruction(r, lang)
    return Reconstruction(id=r["id"], problem=problem, steps=steps)


def _done(s: dict, key: str, lead: str = "") -> dict:
    s["state"] = "DONE"
    s["outcome"]["status"] = mastery_status(s)
    lang = _lang(s)
    text = (lead + " " if lead else "") + tr(key, lang)
    return {"state": "DONE", "expects": "none", "agenda": agenda("DONE", lang), "guard_events": [],
            "message": safetext.static(text, lang=lang, style_kwargs=style_kwargs(s["profile"], lang))}


def enter_transfer(s: dict, h: str, lead: str = "") -> dict:
    """`lead` = an already translated sentence put before the intro (e.g. 'You found the wrong step.')."""
    s["state"] = "TRANSFER"
    qid = pick_transfer_question(s, h)
    s["transfer_q"] = qid
    lang = _lang(s)
    if qid is None:
        if any(not x["correct"] for x in s["outcome"]["transfers"]):
            return enter_handoff(s, s.get("names", {}))  # failed a transfer and no same-type question left
        return _done(s, "no_more", lead)
    text = (lead + " " if lead else "") + tr("transfer_intro", lang)
    return {"state": "TRANSFER", "expects": "transfer_answer", "agenda": agenda("TRANSFER", lang),
            "message": safetext.static(text, lang=lang, style_kwargs=style_kwargs(s["profile"], lang)),
            "question": qview(s["by_id"][qid], lang), "guard_events": []}


# ---------------------------------------------------------------- step 8: RECONSTRUCT, TRANSFER, HANDOFF
RUBRIC_SYS = """You grade a student's explanation of why one step of a worked maths solution is wrong.
Compare it with the expected explanation. Ignore spelling and language (the student may write French, Arabic or
English). "correct" = names the actual error; "partial" = points at the right place but the reason is vague;
"incorrect" = wrong reason or no reason.
Return JSON: {"verdict": "correct|partial|incorrect", "reason": "one sentence for the teacher"}"""
MAX_RECON_ATTEMPTS = 2
MAX_LOOPS = 2


def grade_explanation(r: dict, text: str) -> dict | None:
    steps = "\n".join(f"{i}. {st}" for i, st in enumerate(r["worked_solution"], 1))
    user = (f"Problem: {r['problem']}\nSteps:\n{steps}\nWrong step: {r['error_step']}\n"
            f"Expected explanation: {r['expected_explanation']}\nStudent explanation: {text}")
    try:
        d = llm.ask_json(RUBRIC_SYS, user, purpose="tutor_recon_rubric", max_tokens=512) or {}
    except Exception:  # noqa: BLE001
        return None
    v = str(d.get("verdict", "")).lower()
    return {"verdict": v, "reason": str(d.get("reason", ""))[:300]} if v in ("correct", "partial", "incorrect") else None


def on_reconstruct(s: dict, choice: str | None, text: str | None) -> tuple[dict, Grading]:
    """`choice` = the step number the student says is wrong (1-based); `text` = why.
    The step is graded against the item's error_step (deterministic); the 'why' by the LLM rubric (labelled)."""
    r = s["recon"]
    lang = _lang(s)
    try:
        step = int(str(choice).strip())
    except (TypeError, ValueError):
        raise ValueError("RECONSTRUCT needs `choice` = the number of the wrong step") from None
    if not 1 <= step <= len(r["worked_solution"]):
        raise ValueError(f"step must be between 1 and {len(r['worked_solution'])}")
    s["recon_attempts"] += 1
    found = step == r["error_step"]
    rub = grade_explanation(r, text) if (found and text and text.strip()) else None
    s["outcome"]["reconstruct"].append({"item": r["id"], "step": step, "found": found,
                                        "attempt": s["recon_attempts"], "explanation": text, "rubric": rub})
    if rub:
        grading = Grading(correct=found, method="llm_rubric",
                          label=f"Step checked against the answer key. Explanation graded by the LLM: {rub['verdict']}.")
    else:
        grading = Grading(correct=found, method="answer_key", label="Step checked against the answer key")
    if not found and s["recon_attempts"] < MAX_RECON_ATTEMPTS:
        return {"state": "RECONSTRUCT", "expects": "error_step", "agenda": agenda("RECONSTRUCT", lang),
                "message": txt(s, "recon_retry", step=step), "reconstruction": recon_view(r, lang),
                "guard_events": []}, grading
    lead = tr("recon_found", lang) if found else tr("recon_reveal", lang, step=r["error_step"])
    return enter_transfer(s, s["target"], lead=lead), grading


def on_transfer(s: dict, option: str, names: dict, bank: dict, diag) -> tuple[dict, Grading]:
    """Fresh question: graded by the answer key AND used as diagnosis evidence (independent evidence)."""
    q = s["by_id"][s["transfer_q"]]
    if option not in q["options"]:
        raise ValueError(f"unknown option {option!r}")
    correct = option == q["correct"]
    diag.observe_answer(q["id"], option, None)
    s["outcome"]["transfers"].append({"question_id": q["id"], "option": option, "correct": correct,
                                      "loop": s["loops"]})
    grading = Grading(correct=correct, method="answer_key", label="Checked against the answer key")
    if correct:
        return _done(s, "done_mastered"), grading
    h = s.get("target") or "M0"
    if h == "M0":  # the mastery check after "no misconception" failed: look at the evidence again
        h = diag.top()[0]
        if h == "M0":
            return _done(s, "done_plain"), grading
    if s["loops"] >= MAX_LOOPS:
        return enter_handoff(s, names), grading
    s["loops"] += 1
    s["target"] = h
    s["repair_q"] = q["id"]
    s["last_choice"] = {"option": option, "explanation": None}
    s.pop("error_diag", None)  # new question: diagnose the new error
    mis = next((m for m in bank["misconceptions"] if m["id"] == h), None)
    return enter_hint(s, 1, names, mis, diag.as_dict()), grading


def enter_handoff(s: dict, names: dict) -> dict:
    s["state"] = "HANDOFF"
    s["outcome"]["status"] = "handoff"
    h = s.get("target", "M0")
    o = s["outcome"]
    found = any(r["found"] for r in o["reconstruct"])
    hints = sum(1 for e in s.get("tutor_log", []) if e["state"].startswith("HINT") and e.get("detail"))
    wrong = [t["question_id"] for t in o["transfers"] if not t["correct"]]
    # 3-line note for a human tutor, built by code from session data (no LLM text); rendered per language by api
    s["handoff_data"] = {"h": h, "hints": hints, "loops": s["loops"], "found": found, "wrong": wrong}
    s["handoff_note"] = (f"Likely misconception: {names.get(h, h)}.\n"
                         f"Tried: {hints} hints, {s['loops']} repair loops, find-the-mistake "
                         f"({'found' if found else 'not found'}).\n"
                         f"Still wrong on new questions {', '.join(wrong)}. Please work on this with the student.")
    return {"state": "HANDOFF", "expects": "none", "agenda": agenda("DONE", _lang(s)), "guard_events": [],
            "message": txt(s, "handoff")}


def mastery_status(s: dict) -> str:
    """mastered = found the wrong step in RECONSTRUCT AND solved a fresh transfer question;
    no_misconception = M0 path with a correct transfer; handoff; else in_progress."""
    o = s["outcome"]
    if s.get("state") == "HANDOFF":
        return "handoff"
    transfer_ok = any(t["correct"] for t in o["transfers"])
    if s.get("target") in (None, "M0"):
        return "no_misconception" if transfer_ok else "in_progress"
    if transfer_ok and any(r["found"] for r in o["reconstruct"]):
        return "mastered"
    return "in_progress"


def on_retry(s: dict, option: str, names: dict, mis: dict, posterior: dict, bank: dict) -> tuple[dict, Grading]:
    q = s["by_id"][s["repair_q"]]
    if option not in q["options"]:
        raise ValueError(f"unknown option {option!r}")
    correct = option == q["correct"]
    s.setdefault("retries", []).append({"state": s["state"], "question_id": q["id"], "option": option,
                                        "correct": correct})
    grading = Grading(correct=correct, method="answer_key", label="Checked against the answer key")
    first_answer = s.get("last_choice") is None or not s["last_choice"].get("option")
    s["last_choice"] = {"option": option, "explanation": None}
    level = int(s["state"].split("_")[1])
    if correct and not first_answer:
        return enter_reconstruct(s, bank), grading
    if first_answer:
        if correct:
            return enter_reconstruct(s, bank), grading
        return enter_hint(s, 1, names, mis, posterior), grading
    if level < 3:
        return enter_hint(s, level + 1, names, mis, posterior), grading
    return enter_reconstruct(s, bank), grading
