"""The ONLY module the frontend imports from the engine (see docs/INTERFACE.md).

Every function returns plain dicts that validate against engine/contract.py.
State is held in memory per Streamlit server process (sessions dict).

Implemented for real now (step 4): sessions, diagnosis loop (answers + confidence), next-question
selection, cost, results reading. Tutor hints, summaries and Study Studio arrive in later steps;
until then those functions raise NotImplementedError and the stub pages use engine/api_fake.py.
"""
from __future__ import annotations

import copy
import json
import re
import time
import uuid

from engine import ROOT, bayes, llm
from engine import safetext
from engine.config import cfg
from engine.contract import (AnswerRecord, Agenda, Cost, ExplanationEvidence, Grading, HypProb, LabelProb,
                             MisconceptionView, NextQuestion, QuestionView, SessionState, TutorTurn)

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


def _qview(q: dict, profile: dict) -> QuestionView:
    structured = bool(profile.get("structured_why"))
    why = []
    if structured:
        why = [safetext.static(t) for t in ("I used a rule I remember.", "I worked it out step by step.",
                                            "I compared it with an example.", "I guessed.")]
    return QuestionView(id=q["id"], text=q["text"], options=q["options"], requires_confidence=True,
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


def _agenda(s: dict) -> Agenda:
    d = s["diag"]
    total = d.p["max_questions"]
    step = min(len(d.asked) + 1, total)
    return Agenda(step=step, total=total, next="next question" if not d.done() else "your results")


def _state(sid: str) -> SessionState:
    s = _SESSIONS[sid]
    d: bayes.Diagnoser = s["diag"]
    names = _names()
    top_h, top_p = d.top()
    nq = _next(d, s["pool"])
    cur = s["by_id"].get(nq.question_id) if not nq.stop else None
    return SessionState(session_id=sid, student=s["student"], profile=s["profile"], demo_mode=s["demo"],
                        state=s["state"], agenda=_agenda(s), posterior=_posterior(d),
                        top=HypProb(id=top_h, name_en=names[top_h], prob=round(top_p, 6)),
                        asked=s["asked"], current_question=_qview(cur, s["profile"]) if cur else None,
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
                      "profile": dict(profile or {}), "demo": demo, "state": "DIAGNOSE",
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
    if nq.stop:
        msg = "Thank you. That was the last diagnosis question. Your results are ready."
        expects, nxt = "none", None
    else:
        msg = "Thank you. Your answer is saved. Here is the next question."
        expects, nxt = "answer", _qview(s["by_id"][nq.question_id], s["profile"])
    turn = TutorTurn(session_id=session_id, turn_id=s["turn"], state=s["state"], message=safetext.static(msg),
                     expects=expects, agenda=_agenda(s), question=nxt,
                     grading=Grading(correct=correct, method="answer_key", label="Checked against the answer key"),
                     posterior=_posterior(d), next_question=nq, guard_events=[], explanation_evidence=evidence)
    return turn.model_dump()


def tutor_reply(session_id: str, text: str | None = None, choice: str | None = None) -> dict:
    raise NotImplementedError("tutor turns arrive in step 6 (use engine.api_fake for the stub pages)")


def summary(session_id: str) -> dict:
    raise NotImplementedError("session summary arrives in step 9 (use engine.api_fake)")


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
