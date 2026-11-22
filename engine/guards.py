"""Guards: every tutor-facing generated text passes leak, congruency, math and style checks before display.

- leak: deterministic first (correct option letter, correct option text, SymPy value of the answer), then the
  LLM judge "does this reveal or trivialise the answer?".
- congruency: the LLM judge checks the message against every misconception with posterior > threshold
  ("does this state, imply or exemplify misconception X?").
- math: every 'a = b' and numeric comparison ('<', '>', 'smaller than', 'inférieur à', 'أصغر من') found by regex
  is verified with SymPy; the judge also EXTRACTS claims written in words, which SymPy then verifies.
- style: deterministic linter (engine/style.py) with the active profile's limits, plus a language check (the
  message must be in the student's language: fr / ar / en).
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
   wrong idea as if it were correct. NOT congruent: mentioning the wrong idea in order to question it, or a
   contrasting example that applies the wrong method to DIFFERENT numbers and says the result is wrong.
3. claims: list EVERY equality or comparison between numbers that the message asserts as TRUE, written with
   numbers only. Resolve words to the numbers they mean: "2/5 is smaller than each fraction" about 1/2 and 1/3
   gives [{"lhs": "2/5", "op": "<", "rhs": "1/2"}, {"lhs": "2/5", "op": "<", "rhs": "1/3"}]. Do NOT list results
   the message itself says are wrong. Do not judge whether the claims are true; just extract them.
   op is one of "=", "<", ">", "<=", ">=".
Return JSON: {"reveals_answer": true|false, "leak_reason": "...",
 "congruent": {"M1": true|false, ...}, "congruency_reason": "...",
 "claims": [{"lhs": "...", "op": "...", "rhs": "..."}]}"""


def _judge_model(purpose: str | None = None) -> str:
    """Judge model; config llm.judge_model_by_purpose can override it for one purpose (e.g. the summary judge)."""
    c = cfg()["llm"]
    return (c.get("judge_model_by_purpose") or {}).get(purpose) or c.get("judge_model") or llm.eval_model()


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


_AR_LETTER = re.compile(r"[ء-ي]")
_LAT_LETTER = re.compile(r"[A-Za-zÀ-ÿ]")


_EN_HINT = {"the", "is", "and", "because", "it", "you", "your", "what", "which", "look", "at", "of", "to", "then",
            "with", "this", "that", "are", "do", "does", "how", "many", "add", "same", "they", "true", "false"}
_FR_HINT = {"le", "la", "les", "des", "est", "et", "que", "je", "il", "on", "une", "un", "du", "tu", "ta", "ton",
            "tes", "quel", "quelle", "combien", "font", "vaut", "avec", "pour", "dans", "même", "donc", "regarde",
            "vrai", "faux", "écrit", "additionne", "fraction", "fractions", "dénominateur", "numérateur"}


def language_check(text: str, lang: str | None) -> str | None:
    """Reason the text is not in the requested language (None = ok). Deterministic, part of the style check."""
    if not lang:
        return None
    # 1-2 letter Latin tokens are labels, units or variables (a, b, x, A, s, m, kg, N), not language
    words_only = re.sub(r"(?<![A-Za-zÀ-ÿ])(?:[A-Za-z]{1,2}|[A-Z]{2,})(?![A-Za-zÀ-ÿ])", " ", text)  # + acronyms
    ar, lat = len(_AR_LETTER.findall(text)), len(_LAT_LETTER.findall(words_only))
    if lang == "ar":
        return None if ar and ar / (ar + lat) >= 0.6 else f"not in Arabic ({ar} Arabic vs {lat} Latin letters)"
    if ar:
        return f"contains Arabic script, expected {lang}"
    from engine.detector import detect_language  # lazy: same deterministic detector as the explanation path
    got = detect_language(text)
    words = re.findall(r"[\w']+", text.lower())
    en = sum(w in _EN_HINT for w in words)
    fr = sum(w in _FR_HINT for w in words) + len(re.findall(r"[éèêàçùâîôœ]", text.lower()))
    # reject only on positive evidence: very short or formula-only texts have no language words at all
    if lang == "fr" and (got == "darija" or en > fr):
        return f"expected French, detected {'darija' if got == 'darija' else 'English'}"
    if lang == "en" and (got == "darija" or fr > en):
        return f"expected English, detected {'darija' if got == 'darija' else 'French'}"
    return None


_NEGATED = re.compile(
    r"(?i)\b(?:wrong|incorrect|false|not\s+(?:true|correct|equal)|is\s+not|isn't|faux|fausse|incorrecte?|"
    r"n'est\s+pas|n’est\s+pas|vrai\s+ou\s+faux|true\s+or\s+false|impossible)\b|خطأ|خاطئ|غير\s+صحيح|ليس|≠")


def math_check(text: str, extracted: list | None = None) -> tuple[str, str]:
    """Deterministic: equalities + numeric comparisons found by regex (mathcheck). Plus claims the LLM judge
    extracted from the wording (e.g. 'smaller than each fraction'): the LLM only extracts, SymPy decides."""
    claims = []
    for sent in re.split(r"(?<=[.!?؟;])\s+|\n+", text):
        found = mc.check_equalities(sent) + mc.check_inequalities(sent)
        if any(c["ok"] is False for c in found) and _NEGATED.search(sent):
            # the sentence itself says the statement is wrong ("1/2 + 1/2 = 2/4, which is wrong"): quoted, not asserted
            found = [{**c, "ok": None if c["ok"] is False else c["ok"]} for c in found]
        claims += found
    for c in extracted or []:
        if not isinstance(c, dict):
            continue
        lhs, op, rhs = str(c.get("lhs", "")), str(c.get("op", "")).strip(), str(c.get("rhs", ""))
        ok = mc.equal(lhs, rhs) if op == "=" else mc.compare(lhs, op, rhs)
        if ok is not None:
            claims.append({"claim": f"{lhs} {op} {rhs} (extracted)", "ok": ok})
    bad = [c["claim"] for c in claims if c["ok"] is False]
    if bad:
        return "fail", f"false claims: {bad}"
    if claims:
        return "pass", f"{len(claims)} claims verified with SymPy"
    return "pass", "no checkable claim"


def judge(text: str, q: dict, suspects: dict[str, str], purpose: str = "guard_judge") -> dict:
    opts = "\n".join(f"{k}: {mc.latex_to_plain(v)}" for k, v in q["options"].items())
    mis = "\n".join(f"{k}: {v}" for k, v in suspects.items()) or "(none)"
    user = (f"Question: {mc.latex_to_plain(q['text'])}\nOptions:\n{opts}\nCorrect option: {q['correct']}\n"
            f"Misconceptions to check:\n{mis}\n\nTutor message:\n{text}")
    return llm.ask_json(JUDGE_SYS, user, purpose=purpose, model=_judge_model(), max_tokens=1024) or {}


def check(text: str, q: dict, posterior: dict[str, float], names: dict[str, str],
          style_kwargs: dict | None = None, use_llm: bool = True, lang: str | None = None) -> tuple[list[Check], dict]:
    """Run all four checks. Returns (checks, detail). A check that could not run is reported as 'fail'
    (fail closed), so the SafeText is not shown and the caller regenerates or falls back."""
    thr = cfg().get("guards", {}).get("congruency_threshold", 0.2)
    suspects = {h: names[h] for h, p in posterior.items() if h != "M0" and p > thr}
    detail: dict = {"suspects": list(suspects)}
    checks: list[Check] = []

    viol = style.lint(text, **(style_kwargs or {}))
    wrong_lang = language_check(text, lang)
    if wrong_lang:
        viol.append(wrong_lang)
    checks.append(Check(name="style", status="fail" if viol else "pass", detail="; ".join(viol)))
    det = deterministic_leak(text, q)
    detail["deterministic_leak"] = det
    j = None
    if not det and use_llm:
        try:
            j = judge(text, q, suspects)
        except Exception as e:  # noqa: BLE001  (CacheMiss in demo, API failure): fail closed
            detail["judge_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    detail["judge"] = j
    ms, md = math_check(text, (j or {}).get("claims"))
    checks.append(Check(name="math", status=ms, detail=md))
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


STUDIO_JUDGE_SYS = """You check short texts written for a maths student (flashcards, summary lines). You are a strict
checker, not a writer. For EACH text:
1. congruent: list the ids of the misconceptions below that the text states, implies or uses as if correct.
   Showing a wrong idea in order to say it is wrong is NOT congruent.
2. claims: every equality or comparison between numbers the text asserts as TRUE, numbers only, e.g.
   {"lhs": "1/2+1/4", "op": "=", "rhs": "3/4"}. Do not list results the text itself says are wrong.
Return JSON: {"texts": [{"id": "...", "congruent": ["M1"], "claims": [{"lhs": "...", "op": "...", "rhs": "..."}]}]}"""


def check_studio(texts: dict[str, str], suspects: dict[str, str], lang: str, style_kwargs: dict | None = None,
                 purpose: str = "studio_judge") -> dict[str, list[Check]]:
    """Four checks for Study Studio texts (no graded question, so 'leak' = not applicable), with ONE judge call
    for the whole batch. Fails closed when the judge is unavailable."""
    mis = "\n".join(f"{k}: {v}" for k, v in suspects.items()) or "(none)"
    user = f"Misconceptions:\n{mis}\n\nTexts:\n" + "\n".join(f"[{k}] {v}" for k, v in texts.items())
    try:
        j = llm.ask_json(STUDIO_JUDGE_SYS, user, purpose=purpose, model=_judge_model(purpose), max_tokens=2048) or {}
        verdict = {str(x.get("id", "")).strip("[]"): x for x in j.get("texts", []) if isinstance(x, dict)}
        err = None
    except Exception as e:  # noqa: BLE001
        verdict, err = {}, f"{type(e).__name__}: {str(e)[:100]}"
    out = {}
    for k, text in texts.items():
        viol = style.lint(text, **(style_kwargs or {}))
        wl = language_check(text, lang)
        if wl:
            viol.append(wl)
        v = verdict.get(k)
        ms, md = math_check(text, (v or {}).get("claims"))
        checks = [Check(name="leak", status="not_applicable", detail="no graded question"),
                  Check(name="math", status=ms, detail=md),
                  Check(name="style", status="fail" if viol else "pass", detail="; ".join(viol))]
        if v is None:
            checks.append(Check(name="congruency", status="fail", detail=f"judge unavailable ({err or 'no verdict'})"))
        else:
            hit = [h for h in (v.get("congruent") or []) if h in suspects]
            checks.append(Check(name="congruency", status="fail" if hit else "pass",
                                detail=f"congruent with {hit}" if hit else "checked"))
        out[k] = checks
        _log(text, checks, {"studio": True, "suspects": list(suspects)})
    return out


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
