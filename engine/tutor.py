"""Tutor state machine. Code decides the state and the message type; the LLM only writes the wording.

DIAGNOSE -> HINT_1 -> HINT_2 -> HINT_3 -> RECONSTRUCT -> TRANSFER -> DONE
  the student retries the repair question after each hint; a correct retry skips to RECONSTRUCT
  M0 diagnosed -> TRANSFER directly (mastery check)
RECONSTRUCT grading, TRANSFER grading, loops and HANDOFF: step 8.

Each hint turn = two LLM calls: (1) a structured diagnosis of the student's error (error, faulty step) for the
misconception chosen by bayes.py, (2) the message of the allowed type. Then the guards (engine/guards.py).
On a guard failure: regenerate once with the failure as feedback, then fall back to the human-verified bank hint
of the same level, then to a fixed template. Retries are graded against the answer key; they do not update the
posterior (the same question re-answered after a hint is not independent evidence).
"""
from __future__ import annotations

from engine import guards, llm, mathcheck as mc, safetext
from engine.contract import Agenda, Grading, QuestionView, Reconstruction

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
- Write in {lang}. Maths as plain text (1/3, 2 x 5, -7), no LaTeX.
- Never give the final answer, the correct option letter, or a number equal to the answer.
- Never state or use the student's wrong idea as if it were correct.
- Any equality you write must be true.
- At most {max_words} words per sentence, at most {max_q} question mark(s), no exclamation marks, no emoji,
  no ALL-CAPS words, no praise words.
- Under 60 words in total.
Message type you must write: {hint_type}
Return JSON: {{"message": "..."}}"""


def _plain_q(q: dict) -> str:
    opts = "; ".join(f"{k}: {mc.latex_to_plain(v)}" for k, v in q["options"].items())
    return f"{mc.latex_to_plain(q['text'])} Options: {opts}"


def style_kwargs(profile: dict) -> dict:
    """Active style limits (base rules; the full support-profile toggles arrive in step 10)."""
    kw = {"max_words_per_sentence": int(profile.get("max_words_per_sentence", 25)),
          "neutral": True, "max_questions": 1 if profile.get("one_question_per_message") else 2}
    return kw


def agenda(state: str) -> Agenda:
    i = REPAIR_STEPS.index(state) if state in REPAIR_STEPS else len(REPAIR_STEPS) - 1
    nxt = {"HINT_1": "you try the question again", "HINT_2": "you try the question again",
           "HINT_3": "you try the question again", "RECONSTRUCT": "find the wrong step",
           "TRANSFER": "a new question"}.get(state, "your results")
    return Agenda(step=i + 1, total=len(REPAIR_STEPS), next=nxt)


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
    same = [qid for qid in pool if s["by_id"][qid].get("target") == h]
    return (same or pool or [None])[0]


# ---------------------------------------------------------------- LLM steps
def diagnose_error(q: dict, option: str, explanation: str | None, mis: dict) -> dict:
    user = (f"Question: {_plain_q(q)}\nStudent chose: {option}: {mc.latex_to_plain(q['options'][option])}\n"
            f"Student explanation: {explanation or '(none)'}\n"
            f"Misconception identified by the engine: {mis['name_en']} - {mis.get('description', '')}")
    return llm.ask_json(DIAG_SYS, user, purpose="tutor_diagnosis", max_tokens=1024) or {}


def write_hint(level: int, q: dict, diag: dict, mis: dict, lang: str, kw: dict, feedback: str = "",
               attempt: int = 0) -> str:
    sysmsg = HINT_SYS.format(lang=LANG.get(lang, "English"), max_words=kw["max_words_per_sentence"],
                             max_q=kw["max_questions"], hint_type=HINT_TYPES[level])
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
    lang = s["student"].get("lang", "en")
    kw = style_kwargs(s["profile"])
    events, detail = [], {"level": level}
    last = s["last_choice"]
    try:
        if "error_diag" not in s:
            s["error_diag"] = diagnose_error(q, last["option"], last.get("explanation"), mis)
        diag = s["error_diag"]
        feedback = ""
        for attempt in range(2):  # first draft + one regeneration
            text = write_hint(level, q, diag, mis, lang, kw, feedback, attempt)
            if not text:
                feedback = "empty message"
                continue
            checks, gd = guards.check(text, q, posterior, names, style_kwargs=kw)
            detail[f"attempt{attempt}"] = {"text": text, "checks": [c.model_dump() for c in checks]}
            failed = [c for c in checks if c.status == "fail"]
            if not failed:
                events += guards.events(checks, "shown")
                return safetext.from_guards(text, checks, lang=lang), events, detail
            events += guards.events(checks, "regenerated" if attempt == 0 else "fallback")
            feedback = "; ".join(f"{c.name}: {c.detail}" for c in failed)[:400]
    except Exception as e:  # noqa: BLE001  (CacheMiss in demo mode, API failure)
        detail["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return fallback(q, level, kw), events, detail


def fallback(q: dict, level: int, kw: dict):
    hints = q.get("verified_hints") or []
    if q.get("verified") and len(hints) >= level:
        t = safetext.static(hints[level - 1], origin="verified_bank", style_kwargs=kw, fallback_used=True)
        if t.shown_allowed:
            return t
    return safetext.static("Look again at each step of your working. Check which step uses a rule you are not sure of.",
                           style_kwargs=kw, fallback_used=True)


# ---------------------------------------------------------------- transitions
def qview(q: dict) -> QuestionView:
    return QuestionView(id=q["id"], text=q["text"], options=q["options"], requires_confidence=False)


def begin(s: dict, h: str, names: dict, mis: dict | None, posterior: dict) -> dict:
    """Called when the diagnosis stops. Returns TutorTurn fields (state, message, expects, question, ...)."""
    if h == "M0" or mis is None:
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
        msg = safetext.static("Please answer this question. Then you will get help on it.",
                              style_kwargs=style_kwargs(s["profile"]))
        events, detail = [], {}
    else:
        msg, events, detail = hint_message(s, level, s["target"], names, mis, posterior)
    s.setdefault("tutor_log", []).append({"state": s["state"], "detail": detail})
    return {"state": s["state"], "message": msg, "expects": "retry", "agenda": agenda(s["state"]),
            "question": qview(q), "guard_events": events}


def enter_reconstruct(s: dict, bank: dict) -> dict:
    s["state"] = "RECONSTRUCT"
    s.setdefault("repair_done", []).append(s["repair_q"])
    items = [r for r in bank.get("reconstruction", []) if r["misconception"] == s["target"] and r.get("verified")]
    if not items:
        return enter_transfer(s, s["target"])
    r = items[0]
    s["recon"] = r
    return {"state": "RECONSTRUCT", "expects": "error_step", "agenda": agenda("RECONSTRUCT"),
            "message": safetext.static("Here is a worked solution with one wrong step. Which step is wrong?",
                                       style_kwargs=style_kwargs(s["profile"])),
            "reconstruction": Reconstruction(id=r["id"], problem=r["problem"], steps=r["worked_solution"]),
            "guard_events": []}


def enter_transfer(s: dict, h: str) -> dict:
    s["state"] = "TRANSFER"
    qid = pick_transfer_question(s, h)
    s["transfer_q"] = qid
    kw = style_kwargs(s["profile"])
    if qid is None:
        s["state"] = "DONE"
        return {"state": "DONE", "expects": "none", "agenda": agenda("DONE"), "guard_events": [],
                "message": safetext.static("There are no more questions in the bank for this session.", style_kwargs=kw)}
    return {"state": "TRANSFER", "expects": "transfer_answer", "agenda": agenda("TRANSFER"),
            "message": safetext.static("Here is a new question. Use what you checked in the last steps.",
                                       style_kwargs=kw),
            "question": qview(s["by_id"][qid]), "guard_events": []}


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
