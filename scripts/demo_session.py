"""Scripted demo session: diagnosis -> hints -> retry -> RECONSTRUCT.

Record (live LLM, fills .cache/llm):   .\\.venv\\Scripts\\python.exe scripts\\demo_session.py --record
Replay offline (demo mode, cache only): .\\.venv\\Scripts\\python.exe scripts\\demo_session.py
In demo mode a cache miss raises CacheMiss inside the engine, which falls back to the verified bank text; the
replay reports how many turns used a fallback so a gap in the cache is visible.
The student is fixed (Amira, 7e, French) and answers as an "adds across" (M1) student, with one French explanation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import api, llm  # noqa: E402

TARGET = "M1"
EXPLANATION = "j'ai additionné les numérateurs ensemble et les dénominateurs ensemble"


def show(t: dict) -> None:
    m = t["message"]
    tag = "FALLBACK" if m["fallback_used"] else m["origin"]
    print(f"  [{t['state']}] ({tag}, shown={m['shown_allowed']}) {m['text']}")
    for e in t["guard_events"]:
        if e["status"] == "fail":
            print(f"     guard: {e['summary']} -> {e['action']}")


def run(demo: bool, lang: str = "fr") -> int:
    s = api.start_session({"name": "Amira", "level": "7e", "lang": lang}, demo=demo)
    sid = s["session_id"]
    fallbacks, first = 0, True
    t = None
    while s["state"] == "DIAGNOSE" and s["current_question"]:
        q = s["current_question"]
        bq = api._SESSIONS[sid]["by_id"][q["id"]]  # script only: picks the option a M1 student would choose
        opt = next((o for o, m in bq.get("option_misconception", {}).items() if m == TARGET),
                   next(o for o in bq["options"] if o != bq["correct"]))
        t = api.submit_answer(sid, q["id"], opt, "sure", explanation=EXPLANATION if first else None)
        first = False
        top = max(t["posterior"], key=lambda h: h["prob"])
        print(f"{q['id']}: chose {opt} (sure) -> top {top['id']} {top['prob']:.2f}; "
              f"next IG {t['next_question']['ig_bits'] if t['next_question'] else '-'}")
        if t.get("explanation_evidence"):
            ev = t["explanation_evidence"]
            print(f"  explanation [{ev['lang']}, {ev['method']}] -> {ev['english']}")
        s = api.get_state(sid)
    show(t)
    fallbacks += t["message"]["fallback_used"]
    rq = api._SESSIONS[sid]["by_id"][t["question"]["id"]]
    wrong = next(o for o in rq["options"] if o != rq["correct"] and o != api._SESSIONS[sid]["last_choice"]["option"])
    t = api.tutor_reply(sid, choice=wrong)
    print(f"retry {rq['id']}: {wrong} -> {t['grading']['label']}: correct={t['grading']['correct']}")
    show(t)
    fallbacks += t["message"]["fallback_used"]
    t = api.tutor_reply(sid, choice=rq["correct"])
    print(f"retry {rq['id']}: correct option -> {t['grading']['label']}: correct={t['grading']['correct']}")
    show(t)
    if t.get("reconstruction"):
        for i, st in enumerate(t["reconstruction"]["steps"], 1):
            print(f"     {i}. {st}")
        r = api._SESSIONS[sid]["recon"]  # script only: the student finds the wrong step
        why = {"fr": "on ne peut pas additionner les dénominateurs", "ar": "لا يمكن جمع المقامات",
               "en": "you cannot add the denominators"}[lang]
        t = api.tutor_reply(sid, choice=str(r["error_step"]), text=why)
        print(f"reconstruct: step {r['error_step']} + '{why}' -> {t['grading']['label']}")
        show(t)
    if t["state"] == "TRANSFER":
        tq = api._SESSIONS[sid]["by_id"][t["question"]["id"]]
        t = api.tutor_reply(sid, choice=tq["correct"])
        print(f"transfer {tq['id']}: correct option -> {t['grading']['label']}: correct={t['grading']['correct']}")
        show(t)
    from engine import tutor
    print(f"final state {t['state']}, mastery: {tutor.mastery_status(api._SESSIONS[sid])}")
    c = api.get_state(sid)["cost"]
    print(f"cost: {c['calls']} calls ({c['cached_calls']} cached), {c['prompt_tokens']}+{c['completion_tokens']} "
          f"tokens, {c['label']}; hint fallbacks: {fallbacks}")
    return fallbacks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="live LLM calls (fills the cache)")
    ap.add_argument("--lang", default="fr", choices=["fr", "ar", "en"], help="student language (default fr)")
    a = ap.parse_args()
    n = run(demo=not a.record, lang=a.lang)
    if not a.record and n:
        print(f"WARNING: {n} hint turn(s) used a fallback in demo mode (cache gap?)")
    llm.set_demo_mode(False)
