"""Judge validation: guard decisions vs HUMAN labels in eval/guard_labels.csv -> results/guards.json

The 30 messages in guard_labels.csv were written by us (Claude Code) to cover: safe hints, explicit leaks
(value / option letter), near-trivial scaffolds, messages that endorse a misconception, and contrasting examples,
in EN / FR / AR, on the 4 MAP questions of the bank. The HUMAN fills, per row:
  human_reveals_answer: yes | no
  human_congruent:      the misconception ids the message endorses (e.g. "M1"), or "none"
Rows without both labels are skipped. Nothing is written to results/ until at least one row is labelled,
so the UI can never claim validated guards without human labels.

Usage: .\\.venv\\Scripts\\python.exe eval\\eval_guards.py
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, api, bayes, guards, llm  # noqa: E402

LABELS = ROOT / "eval" / "guard_labels.csv"


def labelled_rows(path: Path = LABELS) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ok = []
    for r in rows:
        leak = r["human_reveals_answer"].strip().lower()
        cong = r["human_congruent"].strip()
        if leak in ("yes", "no") and cong:
            r["_leak"] = leak == "yes"
            r["_cong"] = set() if cong.lower() == "none" else {c.strip() for c in cong.replace(";", ",").split(",")}
            ok.append(r)
    return ok


def binary(pred: list[bool], gold: list[bool]) -> dict:
    tp = sum(p and g for p, g in zip(pred, gold))
    fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold))
    tn = sum(not p and not g for p, g in zip(pred, gold))
    n = len(gold)
    return {"n": n, "positives": tp + fn, "accuracy": round((tp + tn) / n, 4) if n else None,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, default=LABELS)
    a = ap.parse_args()
    rows = labelled_rows(a.labels)
    if not rows:
        print("No labelled rows in eval/guard_labels.csv: fill human_reveals_answer (yes/no) and human_congruent "
              "(e.g. M1, or none). Nothing written.")
        return
    t0 = time.time()
    llm.set_session("eval_guards")
    bank = bayes.load_bank()
    by_id = {q["id"]: q for q in bank["questions"]}
    names = {m["id"]: m["name_en"] for m in api.misconceptions()}
    out, leak_pred, leak_gold, leak_det, cong_pred, cong_gold = [], [], [], [], [], []
    det_all, gold_all, skipped = [], [], []
    for r in rows:
        q = by_id[r["question_id"]]
        sus = [s.strip() for s in r["suspects"].split(",") if s.strip()]
        post = {h: (0.6 / len(sus) if h in sus else 0.4 / (5 - len(sus))) for h in bayes.H}
        checks, detail = guards.check(r["message"], q, post, names, lang=r["lang"])
        st = {c.name: c.status for c in checks}
        judge = detail.get("judge") or {}
        leak = st["leak"] == "fail"
        cong = {h for h in sus if bool((judge.get("congruent") or {}).get(h))}
        det_all.append(bool(detail.get("deterministic_leak")))
        gold_all.append(r["_leak"])
        if detail.get("judge_error"):  # judge unavailable (e.g. daily cap): not counted against the judge
            skipped.append({"id": r["id"], "error": detail["judge_error"]})
            continue
        leak_pred.append(leak)
        leak_gold.append(r["_leak"])
        leak_det.append(bool(detail.get("deterministic_leak")))
        if detail.get("deterministic_leak"):
            out.append({"id": r["id"], "lang": r["lang"], "human_leak": r["_leak"], "guard_leak": True,
                        "deterministic_leak": detail["deterministic_leak"], "human_congruent": sorted(r["_cong"]),
                        "judge_congruent": None, "judge_ran": False, "checks": st})
            continue  # congruency is not judged when the deterministic leak check already blocked the message
        for h in sus:
            cong_pred.append(h in cong)
            cong_gold.append(h in r["_cong"])
        out.append({"id": r["id"], "lang": r["lang"], "human_leak": r["_leak"], "guard_leak": leak,
                    "deterministic_leak": detail.get("deterministic_leak"), "human_congruent": sorted(r["_cong"]),
                    "judge_congruent": sorted(cong), "judge_ran": bool(judge), "checks": st})
    res = {"script": "eval/eval_guards.py",
           "label": "Guard decisions vs human labels (our 30 hand-written test messages, labelled by the team)",
           "created": dt.datetime.now().isoformat(timespec="seconds"), "judge_model": guards._judge_model(),
           "n_labelled": len(rows), "n_total": sum(1 for _ in LABELS.open(encoding="utf-8")) - 1,
           "labels_file": str(a.labels.relative_to(ROOT)) if a.labels.is_absolute() else str(a.labels),
           "leak_full_guard": binary(leak_pred, leak_gold), "leak_deterministic_only": binary(det_all, gold_all),
           "congruency_judge": binary(cong_pred, cong_gold), "judge_unavailable": skipped, "rows": out,
           "caveats": ["Small hand-written test set, not real tutor traffic.",
                       "Leak = deterministic check OR LLM judge; congruency is judged per suspected misconception.",
                       "Rows where the judge could not run (API error / daily cap) are listed in judge_unavailable "
                       "and left out of the judge metrics (in the live tutor they fail closed).",
                       "Congruency is only judged on messages that passed the deterministic leak check."],
           "runtime_s": round(time.time() - t0, 1)}
    from engine.detector import save_json
    save_json(res, ROOT / "results" / "guards.json")
    print(f"labelled {len(rows)}: leak acc {res['leak_full_guard']['accuracy']} "
          f"(recall {res['leak_full_guard']['recall']}), congruency acc {res['congruency_judge']['accuracy']} "
          f"(recall {res['congruency_judge']['recall']}) -> results/guards.json")


if __name__ == "__main__":
    main()
