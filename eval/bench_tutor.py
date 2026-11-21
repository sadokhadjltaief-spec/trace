"""Tutor benchmark with LLM-played students -> results/tutor.json   (SIMULATION PROXY)

Conditions: (A) plain tutor (one LLM, no state machine, no guards), (B) TRACE state machine without guards,
(C) full TRACE (state machine + guards + regenerate + verified fallback).
Each run plants ONE misconception (M1..M4, rotating, with the bank questions for it rotating too):
  the student has already answered the repair question with the option that maps to the misconception;
  up to 3 tutor turns (hint -> student retries); then a fresh transfer question for the same misconception.
Measured: leak rate (DETERMINISTIC check on every tutor message: correct letter, option text, answer value),
transfer pass rate (answer key), tutor turns until a correct retry.
Small on purpose (Groq free tier: 1000 requests/day and 200k tokens/day per model): runs per condition
(team decision 2026-11-21: 5). gpt-oss-20b hit its daily token cap, so by default every role runs on LLM_MODEL
(gpt-oss-120b): tutor, students (--student-model) and guard judge (config llm.judge_model).
Runs are interleaved A, B, C per planted student, so stopping early keeps the conditions balanced. If the daily cap
is hit, the benchmark stops and saves what it has (stopped_early).
Diagnosis is benchmarked separately (bench_diagnosis.py); RECONSTRUCT is not part of this benchmark.

Usage: .\\.venv\\Scripts\\python.exe eval\\bench_tutor.py [--runs 10]
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, api, bayes, guards, llm, tutor  # noqa: E402
from engine import detector as det  # noqa: E402
from engine import mathcheck as mc  # noqa: E402

MAX_TURNS = 3
STUDENT_MODEL: str | None = None  # set in main(); default LLM_MODEL

STUDENT_SYS = """You play a 12-year-old maths student in a simulation. You hold this misconception:
"{name}: {description}"
Here is how real students with this misconception explained their answers:
{examples}
Stay in character. Keep using the misconception unless the tutor's message genuinely makes you see why it is
wrong. Do not guess randomly; reason the way this student would.
Return JSON: {{"option": "A|B|C|D", "explanation": "one short sentence in the student's words"}}"""

PLAIN_SYS = """You are a helpful maths tutor. A student answered the question below. Help them with their mistake.
Keep it under 60 words. Return JSON: {"message": "..."}"""


def wilson(k: int, n: int, z: float = 1.96):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def qtext(q: dict) -> str:
    return f"{mc.latex_to_plain(q['text'])}\n" + "\n".join(f"{k}: {mc.latex_to_plain(v)}" for k, v in q["options"].items())


def student_answer(q: dict, mis: dict, examples: list[str], history: list[str], run: int, step: str) -> dict:
    sysmsg = STUDENT_SYS.format(name=mis["name_en"], description=mis.get("description", ""),
                                examples="\n".join(f"- {e}" for e in examples))
    user = ("Conversation so far:\n" + "\n".join(history) + "\n\n" if history else "") + f"Question:\n{qtext(q)}"
    d = llm.ask_json(sysmsg, user, purpose="bench_student", model=STUDENT_MODEL, temperature=0.7,
                     seed_tag=f"run{run}_{step}", max_tokens=512) or {}
    opt = str(d.get("option", "")).strip().upper()[:1]
    return {"option": opt if opt in q["options"] else "", "explanation": str(d.get("explanation", ""))}


def plain_message(q: dict, answer: dict, history: list[str]) -> str:
    user = (f"Question:\n{qtext(q)}\nStudent answer: {answer['option']}. Student explanation: {answer['explanation']}\n"
            + ("Conversation so far:\n" + "\n".join(history) if history else ""))
    d = llm.ask_json(PLAIN_SYS, user, purpose="bench_plain_tutor", max_tokens=1024) or {}
    return str(d.get("message", "")).strip()


def run_one(cond: str, run: int, h: str, rq: dict, tq: dict, bank: dict, names: dict, examples: list[str]) -> dict:
    mis = next(m for m in bank["misconceptions"] if m["id"] == h)
    wrong = next(o for o, m in rq["option_misconception"].items() if m == h)
    first = {"option": wrong, "explanation": examples[0]}
    s = {"by_id": {rq["id"]: rq}, "repair_q": rq["id"], "student": {"lang": "en"}, "profile": {},
         "last_choice": first, "target": h}
    post = {k: (0.8 if k == h else 0.05) for k in bayes.H}
    history = [f"Student chose {wrong}: {first['explanation']}"]
    msgs, solved_at, fallbacks, answer = [], None, 0, first
    for turn in range(1, MAX_TURNS + 1):
        if cond == "A":
            text = plain_message(rq, answer, history[1:])
        elif cond == "B":
            if "error_diag" not in s:
                s["error_diag"] = tutor.diagnose_error(rq, first["option"], first["explanation"], mis)
            text = tutor.write_hint(turn, rq, s["error_diag"], mis, "en", tutor.style_kwargs({}))
        else:
            st, _, _ = tutor.hint_message(s, turn, h, names, mis, post)
            text, fallbacks = st.text, fallbacks + st.fallback_used
        leak = guards.deterministic_leak(text, rq)
        msgs.append({"turn": turn, "text": text, "deterministic_leak": leak})
        history.append(f"Tutor: {text}")
        answer = student_answer(rq, mis, examples, history, run, f"{cond}_t{turn}")
        history.append(f"Student chose {answer['option']}: {answer['explanation']}")
        if answer["option"] == rq["correct"]:
            solved_at = turn
            break
    t_ans = student_answer(tq, mis, examples, history + ["Tutor: Here is a new question."], run, f"{cond}_transfer")
    return {"condition": cond, "run": run, "misconception": h, "repair_q": rq["id"], "transfer_q": tq["id"],
            "messages": msgs, "solved_at_turn": solved_at, "transfer_option": t_ans["option"],
            "transfer_correct": t_ans["option"] == tq["correct"], "fallbacks": fallbacks}


def summarise(rows: list[dict]) -> dict:
    msgs = [m for r in rows for m in r["messages"]]
    leaks = sum(bool(m["deterministic_leak"]) for m in msgs)
    runs_leak = sum(any(m["deterministic_leak"] for m in r["messages"]) for r in rows)
    tr = sum(r["transfer_correct"] for r in rows)
    solved = [r["solved_at_turn"] for r in rows if r["solved_at_turn"]]
    return {"runs": len(rows), "tutor_messages": len(msgs),
            "leak_rate_per_message": round(leaks / len(msgs), 4) if msgs else None,
            "leak_rate_per_message_ci95": wilson(leaks, len(msgs)),
            "runs_with_a_leak": runs_leak,
            "transfer_pass_rate": round(tr / len(rows), 4) if rows else None,
            "transfer_pass_ci95": wilson(tr, len(rows)),
            "retry_solved_rate": round(len(solved) / len(rows), 4) if rows else None,
            "mean_turns_when_solved": round(sum(solved) / len(solved), 2) if solved else None,
            "fallbacks_used": sum(r["fallbacks"] for r in rows)}


def daily_cap_hit(since: float) -> bool:
    con = llm._db()
    n = con.execute("SELECT COUNT(*) FROM llm_calls WHERE ts >= ? AND session = 'bench_tutor' "
                    "AND error LIKE '%daily cap%'", (since,)).fetchone()[0]
    con.close()
    return n > 0


def main():
    global STUDENT_MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--student-model", default=None, help="default: LLM_MODEL")
    a = ap.parse_args()
    STUDENT_MODEL = a.student_model or llm.default_model()
    t0 = time.time()
    llm.set_session("bench_tutor")
    bank = bayes.load_bank()
    qs = [q for q in bank["questions"] if q.get("verified")]
    names = {m["id"]: m["name_en"] for m in api.misconceptions()}
    df = det.load_map()
    plan = []
    for i in range(a.runs):
        h = ["M1", "M2", "M3", "M4"][i % 4]
        cand = [q for q in qs if q["target"] == h and any(m == h for m in q["option_misconception"].values())]
        rq = cand[(i // 4) % len(cand)]
        tq = cand[((i // 4) + 1) % len(cand)]
        lab = df[df.label == h].sample(3, random_state=42 + i)
        plan.append((i, h, rq, tq, [str(e) for e in lab.StudentExplanation]))
    rows, stopped = [], None
    for i, h, rq, tq, ex in plan:
        if stopped:
            break
        trio = []
        for cond in ("A", "B", "C"):
            t_run = time.time()
            try:
                r = run_one(cond, i, h, rq, tq, bank, names, ex)
            except Exception as e:  # noqa: BLE001
                r = {"condition": cond, "run": i, "error": f"{type(e).__name__}: {str(e)[:160]}"}
            if daily_cap_hit(t_run):
                stopped = f"Groq daily token cap hit during run {i} ({cond}); runs from {i} on are not counted."
                break
            trio.append(r)
            print(f"{cond} run {i} {h} {rq['id']}->{tq['id']}: "
                  + (r.get("error") or f"solved_at={r['solved_at_turn']} transfer={r['transfer_correct']} "
                                       f"leaks={sum(bool(m['deterministic_leak']) for m in r['messages'])}"), flush=True)
        if not stopped:
            rows += trio  # only complete A/B/C trios are kept
    ok = [r for r in rows if "error" not in r]
    res = {"script": "eval/bench_tutor.py",
           "label": "SIMULATION PROXY: LLM-played students, small sample (free-tier limits)",
           "created": dt.datetime.now().isoformat(timespec="seconds"),
           "runs_per_condition_planned": a.runs,
           "runs_per_condition_completed": len({r["run"] for r in rows}), "stopped_early": stopped,
           "max_tutor_turns": MAX_TURNS,
           "models": {"tutor": llm.default_model(), "student": STUDENT_MODEL, "judge": guards._judge_model()},
           "conditions": {"A": "plain tutor (no state machine, no guards)", "B": "TRACE state machine, no guards",
                          "C": "full TRACE (state machine + guards + fallback)"},
           "summary": {c: summarise([r for r in ok if r["condition"] == c]) for c in ("A", "B", "C")},
           "errors": [r for r in rows if "error" in r], "runs": ok,
           "caveats": ["Simulated students (an LLM playing a misconception) are a proxy, not real learners.",
                       f"{a.runs} runs per condition: confidence intervals are wide; differences may be noise.",
                       "Leak = deterministic check only (letter, option text, answer value); it misses paraphrased leaks.",
                       "Starts after the diagnosis; RECONSTRUCT is not exercised here."],
           "runtime_s": round(time.time() - t0, 1)}
    det.save_json(res, ROOT / "results" / "tutor.json")
    for c, sm in res["summary"].items():
        print(c, sm)
    print(f"wrote results/tutor.json in {res['runtime_s']}s")


if __name__ == "__main__":
    main()
