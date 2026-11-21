"""Guards: every tutor-facing generated text passes leak, congruency, math and style checks before display.

- leak: deterministic first (correct option letter, correct option text, SymPy value of the answer), then the
  LLM judge "does this reveal or trivialise the answer?".
- congruency: the LLM judge checks the message against every misconception with posterior > threshold
  ("does this state, imply or exemplify misconception X?").
- math: every simple 'a = b' claim is verified with SymPy (engine/mathcheck.py).
- style: deterministic linter (engine/style.py) with the active profile's limits.
Leak and congruency share ONE judge call (free tier: halves the request count). Every decision is logged to SQLite
(table guard_log in .cache/trace.db). The judges are NOT validated yet: eval/eval_guards.py needs human labels.
"""
from __future__ import annotations

import json
import re
import time

from engine import llm, mathcheck as mc, style
from engine.config import cfg
from engine.contract import Check, GuardEvent

_LETTER = re.compile(r"(?i)\b(?:option|answer|choice|réponse|reponse|choix|الخيار|الإجابة)\s*[:(]?\s*([A-D])\b")

JUDGE_SYS = """You check one message that a maths tutor wants to send to a student who is retrying a question.
You are a strict safety check, not a writer.
1. reveals_answer: true if the message states the final answer, names the correct option, or does so much of the
   work that only a trivial step is left (that trivialises the question).
2. For each listed misconception: true if the message states, implies, or gives an example that follows that
   wrong idea as if it were correct. Mentioning the wrong idea in order to question it is NOT congruent.
Return JSON: {"reveals_answer": true|false, "leak_reason": "...",
 "congruent": {"M1": true|false, ...}, "congruency_reason": "..."}"""


def _judge_model() -> str:
    return cfg()["llm"].get("judge_model") or llm.eval_model()


def deterministic_leak(text: str, q: dict) -> list[str]:
    """Reasons the text leaks the answer to question q (empty = no deterministic leak)."""
    why = []
    correct_txt = q["options"][q["correct"]]
    for m in _LETTER.finditer(text):
        if m.group(1).upper() == q["correct"]:
            why.append(f"names the correct option {q['correct']}")
    hits = mc.mentions_value(text, correct_txt, exclude_from=q["text"])
    if hits:
        why.append(f"contains the answer value {hits}")
    plain = mc.latex_to_plain(correct_txt).strip().lower()
    if mc.value(correct_txt) is None and len(plain) > 2 and plain in mc.latex_to_plain(text).lower():
        why.append("contains the correct option text")
    return why


def math_check(text: str) -> tuple[str, str]:
    claims = mc.check_equalities(text)
    bad = [c["claim"] for c in claims if c["ok"] is False]
    if bad:
        return "fail", f"false equalities: {bad}"
    if claims:
        return "pass", f"{len(claims)} equalities verified with SymPy"
    return "pass", "no checkable equality"


def judge(text: str, q: dict, suspects: dict[str, str], purpose: str = "guard_judge") -> dict:
    opts = "\n".join(f"{k}: {mc.latex_to_plain(v)}" for k, v in q["options"].items())
    mis = "\n".join(f"{k}: {v}" for k, v in suspects.items()) or "(none)"
    user = (f"Question: {mc.latex_to_plain(q['text'])}\nOptions:\n{opts}\nCorrect option: {q['correct']}\n"
            f"Misconceptions to check:\n{mis}\n\nTutor message:\n{text}")
    return llm.ask_json(JUDGE_SYS, user, purpose=purpose, model=_judge_model(), max_tokens=1024) or {}


def check(text: str, q: dict, posterior: dict[str, float], names: dict[str, str],
          style_kwargs: dict | None = None, use_llm: bool = True) -> tuple[list[Check], dict]:
    """Run all four checks. Returns (checks, detail). A check that could not run is reported as 'fail'
    (fail closed), so the SafeText is not shown and the caller regenerates or falls back."""
    thr = cfg().get("guards", {}).get("congruency_threshold", 0.2)
    suspects = {h: names[h] for h, p in posterior.items() if h != "M0" and p > thr}
    detail: dict = {"suspects": list(suspects)}
    checks: list[Check] = []

    viol = style.lint(text, **(style_kwargs or {}))
    checks.append(Check(name="style", status="fail" if viol else "pass", detail="; ".join(viol)))
    ms, md = math_check(text)
    checks.append(Check(name="math", status=ms, detail=md))

    det = deterministic_leak(text, q)
    detail["deterministic_leak"] = det
    j = None
    if not det and use_llm:
        try:
            j = judge(text, q, suspects)
        except Exception as e:  # noqa: BLE001  (CacheMiss in demo, API failure): fail closed
            detail["judge_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    detail["judge"] = j
    if det:
        checks.append(Check(name="leak", status="fail", detail="deterministic: " + "; ".join(det)))
    elif j is None:
        checks.append(Check(name="leak", status="fail", detail="LLM judge did not run (fail closed)"))
    else:
        leak = bool(j.get("reveals_answer"))
        checks.append(Check(name="leak", status="fail" if leak else "pass",
                            detail=("LLM judge: " + str(j.get("leak_reason", "")))[:300]))
    if not suspects:
        checks.append(Check(name="congruency", status="pass", detail="no misconception above threshold"))
    elif j is None:
        checks.append(Check(name="congruency", status="fail",
                            detail="not checked (deterministic leak or judge unavailable)"))
    else:
        cong = j.get("congruent") or {}
        hit = [h for h in suspects if bool(cong.get(h))]
        checks.append(Check(name="congruency", status="fail" if hit else "pass",
                            detail=(f"congruent with {hit}: " if hit else "") + str(j.get("congruency_reason", ""))[:300]))
    _log(text, checks, detail)
    return checks, detail


def events(checks: list[Check], action: str) -> list[GuardEvent]:
    """One GuardEvent per failed check (action = what the tutor did next), or one 'pass' per check when shown."""
    now = time.time()
    failed = [c for c in checks if c.status == "fail"]
    if failed:
        return [GuardEvent(ts=now, check=c.name, status="fail", action=action,
                           summary=f"message blocked by {c.name}: {c.detail[:100]}") for c in failed]
    return [GuardEvent(ts=now, check=c.name, status="pass", action="shown", summary=c.detail[:100] or "pass")
            for c in checks]


def _log(text: str, checks: list[Check], detail: dict) -> None:
    try:
        con = llm._db()
        con.execute("CREATE TABLE IF NOT EXISTS guard_log(ts REAL, session TEXT, text TEXT, checks TEXT, detail TEXT)")
        con.execute("INSERT INTO guard_log VALUES (?,?,?,?,?)",
                    (time.time(), llm._session_id, text, json.dumps([c.model_dump() for c in checks]),
                     json.dumps(detail, ensure_ascii=False, default=str)))
        con.commit()
        con.close()
    except Exception:  # noqa: BLE001  logging must never break a turn
        pass
