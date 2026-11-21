"""Diagnosis benchmark (no LLM) -> results/diagnosis.json

Simulated students: true hypothesis drawn uniformly from H; each answer is sampled from the bank's
likelihood table (defaults + MAP frequencies) mixed with `noise` uniform answers.
Conditions: info-gain selection vs a fixed interleaved order vs a random order.
PROXY: the simulated world uses the same likelihood model as the engine (plus noise), so these numbers
are optimistic about real students. The real-data evidence is the detector evaluation on MAP.

Usage: .\\.venv\\Scripts\\python.exe eval\\bench_diagnosis.py [--n 1000] [--sens-n 300]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT  # noqa: E402
from engine.bayes import H, Diagnoser, build_table, load_bank, params  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(float(c - half), 4), round(float(c + half), 4)]


def mean_ci(x) -> dict:
    x = np.asarray(x, dtype=float)
    m, se = x.mean(), x.std(ddof=1) / np.sqrt(len(x))
    return {"mean": round(float(m), 3), "ci95": [round(float(m - 1.96 * se), 3), round(float(m + 1.96 * se), 3)]}


def fixed_order(questions: list[dict]) -> list[str]:
    """Round-robin over target misconceptions in bank order (a reasonable teacher-style fixed test)."""
    by_m: dict[str, list[str]] = {}
    for q in questions:
        by_m.setdefault(q["target"], []).append(q["id"])
    order, i = [], 0
    while any(by_m.values()):
        for m in sorted(by_m):
            if by_m[m]:
                order.append(by_m[m].pop(0))
        i += 1
    return order


def simulate(world, engine_table, engine_p, condition, n, noise, rng, order):
    qids = list(world.questions)
    rows = []
    for _ in range(n):
        true_h = H[rng.integers(len(H))]
        d = Diagnoser(engine_table, p=engine_p)
        rand_order = list(rng.permutation(qids))
        while not d.done():
            if condition == "info_gain":
                qid = d.next_question()["question"]
            else:
                seq = order if condition == "fixed" else rand_order
                qid = next((q for q in seq if q not in d.asked), None)
            if qid is None:
                break
            opts = list(world.questions[qid]["options"])
            pr = np.array([world.L[qid][true_h][a] for a in opts])
            pr = (1 - noise) * pr + noise / len(opts)
            d.observe_answer(qid, opts[rng.choice(len(opts), p=pr)])
        top, conf = d.top()
        rows.append({"true": true_h, "pred": top, "n_q": len(d.asked), "reached": conf >= engine_p["stop_threshold"]})
    return rows


def summarise(rows) -> dict:
    n = len(rows)
    k = sum(r["pred"] == r["true"] for r in rows)
    reached = [r for r in rows if r["reached"]]
    out = {"n_students": n, "accuracy": round(k / n, 4), "accuracy_ci95": wilson(k, n),
           "questions_used": mean_ci([r["n_q"] for r in rows]),
           "reached_threshold_rate": round(len(reached) / n, 4),
           "reached_threshold_ci95": wilson(len(reached), n),
           "accuracy_when_threshold_reached": round(sum(r["pred"] == r["true"] for r in reached) / len(reached), 4)
           if reached else None,
           "per_true_hypothesis_accuracy": {}}
    for h in H:
        sub = [r for r in rows if r["true"] == h]
        if sub:
            out["per_true_hypothesis_accuracy"][h] = round(sum(r["pred"] == h for r in sub) / len(sub), 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--sens-n", type=int, default=300)
    ap.add_argument("--noise", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    t0 = time.time()

    bank = load_bank()  # excludes questions blocked by an unconfirmed crosswalk mapping
    qs = bank["questions"]
    base = params()
    world = build_table(qs)
    order = fixed_order(qs)
    res = {"script": "eval/bench_diagnosis.py", "label": "SIMULATION PROXY (simulated students, same model family as the engine)",
           "created": dt.datetime.now().isoformat(timespec="seconds"),
           "git_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, encoding="utf-8",
                                        cwd=ROOT).stdout.strip(),
           "seed": a.seed, "noise": a.noise, "hypotheses": H,
           "bank_questions": [q["id"] for q in qs],
           "excluded_questions": "questions with blocked_by (unconfirmed crosswalk) are excluded",
           "fixed_order": order, "params": {k: base[k] for k in ("p_hit", "p_correct_m0", "p_correct_despite",
                                                                 "eps", "stop_threshold", "max_questions", "use_map_data")},
           "likelihood_sources": world.data_usage(),
           "caveats": ["World and engine share the likelihood model: optimistic vs real students.",
                       "Confidence taps and explanations are NOT simulated here (answers only).",
                       "M0 means 'none of M1..M4'; its MAP-based rows include students with other misconceptions.",
                       "Bank review pending: unverified hints do not affect this benchmark (answers only)."]}

    res["conditions"] = {}
    for cap_name, cap in (("live_cap_5", base["max_questions"]), ("no_cap", len(qs))):
        res["conditions"][cap_name] = {}
        for cond in ("info_gain", "fixed", "random"):
            rng = np.random.default_rng(a.seed)  # same student draws per condition
            rows = simulate(world, world, params(max_questions=cap), cond, a.n, a.noise, rng, order)
            res["conditions"][cap_name][cond] = summarise(rows)
            s = res["conditions"][cap_name][cond]
            print(f"{cap_name:11s} {cond:9s} acc={s['accuracy']:.3f} {s['accuracy_ci95']} "
                  f"q={s['questions_used']['mean']:.2f} reached={s['reached_threshold_rate']:.3f}")

    # ablation: engine ignores MAP frequencies (defaults only) while the world uses them
    rng = np.random.default_rng(a.seed)
    rows = simulate(world, build_table(qs, use_map_data=False), params(use_map_data=False), "info_gain",
                    a.n, a.noise, rng, order)
    res["ablation_engine_without_map_data"] = summarise(rows)
    print(f"ablation no MAP data: acc={res['ablation_engine_without_map_data']['accuracy']:.3f}")

    # sensitivity: engine hyperparameters misspecified vs the fixed world, and world noise
    sens = []
    for noise in (0.1, 0.2, 0.3):
        for p_hit in (0.5, 0.6, 0.7, 0.8, 0.9):
            for pcd in (0.15, 0.3, 0.45):
                ep = params(p_hit=p_hit, p_correct_despite=pcd)
                rng = np.random.default_rng(a.seed)
                rows = simulate(world, build_table(qs, p_hit=p_hit, p_correct_despite=pcd), ep, "info_gain",
                                a.sens_n, noise, rng, order)
                s = summarise(rows)
                sens.append({"world_noise": noise, "engine_p_hit": p_hit, "engine_p_correct_despite": pcd,
                             "accuracy": s["accuracy"], "accuracy_ci95": s["accuracy_ci95"],
                             "questions_used": s["questions_used"]["mean"],
                             "reached_threshold_rate": s["reached_threshold_rate"]})
    accs = [x["accuracy"] for x in sens]
    res["sensitivity"] = {"n_students_each": a.sens_n, "condition": "info_gain, cap 5",
                          "accuracy_min": min(accs), "accuracy_max": max(accs), "grid": sens}
    print(f"sensitivity: accuracy range {min(accs):.3f} - {max(accs):.3f} over {len(sens)} configs")

    res["runtime_s"] = round(time.time() - t0, 1)
    out = ROOT / "results" / "diagnosis.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} in {res['runtime_s']}s")


if __name__ == "__main__":
    main()
