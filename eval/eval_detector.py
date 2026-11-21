"""Detector evaluation on REAL student data (MAP) -> results/detector.json

Split: stratified 80/20 of the labelled MAP train file (seed 42), labels = M0, M1..M4, other.
- TF-IDF: trained on the 80 %, evaluated on the full 20 % held-out set (and on the 4 bank questions).
- LLM variants (zero-shot, few-shot) + TF-IDF + combined: on a fixed sample of 400 held-out rows,
  label-balanced (60 per M1..M4, 80 M0, 80 other) so the rare misconception classes are measurable.
  LLM = EVAL_MODEL, batched several items per call (Groq free tier: 1000 requests/day, 8000 tokens/min).
Metrics: top-1 accuracy, MAP@3, macro-F1, recall on True_Misconception rows (right answer, flawed reasoning):
  "flaw recall" = predicted anything but M0; "exact recall" = predicted the exact label.

Usage: .\\.venv\\Scripts\\python.exe eval\\eval_detector.py [--no-llm]
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, detector as det, llm  # noqa: E402
from engine.config import cfg  # noqa: E402

L = det.LABELS
SEED = 42
BANK_MAP_QIDS = [33472, 32833, 89443, 31778]


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(float(c - h), 4), round(float(c + h), 4)]


def metrics(y: list[str], P: np.ndarray, cats: pd.Series) -> dict:
    y = np.array(y)
    yi = np.array([L.index(v) for v in y])
    order = np.argsort(-P, axis=1)
    pred = order[:, 0]
    acc = float((pred == yi).mean())
    ranks = [list(order[i, :3]).index(yi[i]) + 1 if yi[i] in order[i, :3] else 0 for i in range(len(yi))]
    map3 = float(np.mean([1 / r if r else 0 for r in ranks]))
    present = sorted(set(yi))
    mf1 = float(f1_score(yi, pred, labels=present, average="macro", zero_division=0))
    per_class_f1 = dict(zip([L[i] for i in present],
                            map(float, f1_score(yi, pred, labels=present, average=None, zero_division=0))))
    tm = (cats == "True_Misconception").to_numpy()
    flaw_k = int((pred[tm] != L.index("M0")).sum())
    exact_k = int((pred[tm] == yi[tm]).sum())
    n_tm = int(tm.sum())
    tm_ours = tm & np.isin(yi, [1, 2, 3, 4])
    return {"n": int(len(y)), "accuracy": round(acc, 4), "accuracy_ci95": wilson(int((pred == yi).sum()), len(y)),
            "map_at_3": round(map3, 4), "macro_f1": round(mf1, 4),
            "per_class_f1": {k: round(v, 4) for k, v in per_class_f1.items()},
            "true_misconception_rows": n_tm,
            "true_misconception_flaw_recall": round(flaw_k / n_tm, 4) if n_tm else None,
            "true_misconception_flaw_recall_ci95": wilson(flaw_k, n_tm),
            "true_misconception_exact_recall": round(exact_k / n_tm, 4) if n_tm else None,
            "true_misconception_rows_M1_M4": int(tm_ours.sum()),
            "true_misconception_exact_recall_M1_M4":
                round(float((pred[tm_ours] == yi[tm_ours]).mean()), 4) if tm_ours.any() else None,
            "confusion_matrix": {"labels": L, "rows_true_cols_pred":
                                 confusion_matrix(yi, pred, labels=list(range(len(L)))).tolist()}}


def sample_balanced(test: pd.DataFrame, n_total: int) -> pd.DataFrame:
    """All held-out True_Misconception rows first (the key case), then fill label quotas."""
    quota = {"M1": 60, "M2": 60, "M3": 60, "M4": 60, "M0": 80, "other": 80}
    scale = n_total / sum(quota.values())
    tm = test[test.Category == "True_Misconception"]
    parts = [tm]
    for lab, q in quota.items():
        need = int(round(q * scale)) - int((tm.label == lab).sum())
        pool = test[(test.label == lab) & (test.Category != "True_Misconception")]
        if need > 0:
            parts.append(pool.sample(min(len(pool), need), random_state=SEED))
    return pd.concat(parts).sample(frac=1, random_state=SEED)


def run_llm(sample: pd.DataFrame, index: det.ExampleIndex | None, batch: int, purpose: str):
    model = llm.eval_model()
    items = [{"id": str(r.row_id), "question": r.QuestionText, "answer": r.MC_Answer, "correct": bool(r.is_correct),
              "explanation": r.StudentExplanation, "qid": r.QuestionId} for r in sample.itertuples()]
    chunks = [items[i:i + batch] for i in range(0, len(items), batch)]
    reqs_done, rankings, failed_calls = 0, {}, 0
    t0 = time.time()
    for ch in chunks:
        ex = {it["id"]: index.nearest(it["qid"], it["explanation"], cfg()["detector"]["fewshot_k"])
              for it in ch} if index else None
        try:
            rankings.update(det.llm_rank(ch, ex, model=model, purpose=purpose))
        except Exception as e:  # noqa: BLE001
            failed_calls += 1
            print(f"  {purpose}: call failed: {type(e).__name__}: {str(e)[:120]}")
        reqs_done += 1
        if reqs_done % 5 == 0:
            print(f"  {purpose}: {reqs_done}/{len(chunks)} calls, {time.time() - t0:.0f}s")
    P, missing = [], 0
    for it in items:
        rk = rankings.get(it["id"])
        if not rk:
            missing += 1
            P.append(np.full(len(L), 1 / len(L)))  # unparsed item counts as a uniform (almost surely wrong) guess
        else:
            P.append(det.rank_to_dist(rk))
    return np.array(P), {"calls": len(chunks), "failed_calls": failed_calls, "items_missing": missing,
                         "items_per_call": batch, "model": model}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    df = det.load_map()
    train, test = train_test_split(df, test_size=0.2, random_state=SEED, stratify=df.label)
    print(f"train {len(train)}  test {len(test)}  labels {df.label.value_counts().to_dict()}")
    model = det.train_tfidf(train)
    P_test = det.proba(model, det.map_frame(test))
    res = {"script": "eval/eval_detector.py",
           "label": "REAL student data (MAP, English, UK grades 4-8). Not state of the art: top Kaggle MAP@3 > 0.94 "
                    "with large fine-tuned models; ours is a cheap detector that runs live inside the tutor.",
           "created": dt.datetime.now().isoformat(timespec="seconds"),
           "git_commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                        encoding="utf-8", cwd=ROOT).stdout.strip(),
           "seed": SEED, "label_mapping": {"M1-M4": det.MAP_TO_M, "other": "any other MAP misconception",
                                           "M0": "no misconception label (Correct / Neither)"},
           "split": {"train": len(train), "test": len(test), "stratified_by": "label"},
           "tfidf_full_test": metrics(list(test.label), P_test, test.Category)}
    bank = test.QuestionId.isin(BANK_MAP_QIDS).to_numpy()
    res["tfidf_full_test_bank_questions"] = metrics(list(test.label[bank]), P_test[bank], test.Category[bank])
    print("tfidf full test:", {k: res["tfidf_full_test"][k] for k in ("accuracy", "map_at_3", "macro_f1",
                                                                     "true_misconception_flaw_recall")})

    n = cfg()["detector"]["eval_sample"]
    sample = sample_balanced(test, n)
    pos = test.index.get_indexer(sample.index)
    P_tf_s = P_test[pos]
    res["llm_sample"] = {"n": len(sample), "composition": sample.label.value_counts().to_dict(),
                         "true_misconception_rows": int((sample.Category == "True_Misconception").sum()),
                         "variants": {"tfidf": metrics(list(sample.label), P_tf_s, sample.Category)}}
    if not a.no_llm:
        idx = det.ExampleIndex.build(train)
        P_zero, info_zero = run_llm(sample, None, cfg()["detector"]["batch_zeroshot"], "eval_detector_zeroshot")
        res["llm_sample"]["variants"]["llm_zero_shot"] = {**metrics(list(sample.label), P_zero, sample.Category),
                                                          "run": info_zero}
        P_few, info_few = run_llm(sample, idx, cfg()["detector"]["batch_fewshot"], "eval_detector_fewshot")
        res["llm_sample"]["variants"]["llm_few_shot"] = {**metrics(list(sample.label), P_few, sample.Category),
                                                         "run": info_few}
        res["llm_sample"]["variants"]["combined"] = metrics(list(sample.label), (P_tf_s + P_few) / 2,
                                                            sample.Category)
    for k, v in res["llm_sample"]["variants"].items():
        print(f"sample {k:14s} acc={v['accuracy']} map3={v['map_at_3']} mf1={v['macro_f1']} "
              f"tm_flaw={v['true_misconception_flaw_recall']} (n_tm={v['true_misconception_rows']})")
    res["caveats"] = [
        "LLM variants ran on a ~400-row sample: ALL held-out True_Misconception rows + label quotas "
        "(60 per M1..M4, 80 M0, 80 other), not the natural class mix; compare variants on it.",
        "MAP@3 here is over our 6 labels (M0, M1-M4, other), NOT the Kaggle ~65-label task: not comparable "
        "to Kaggle leaderboard scores.",
        "LLM items were batched (5 few-shot / 20 zero-shot per call) to fit the free-tier request budget; "
        "live use classifies one explanation per call.",
        f"LLM variants used EVAL_MODEL ({llm.eval_model()}); the live tutor uses LLM_MODEL.",
        "M1-M4 labels exist only on 4 MAP questions; Eedi bank questions have no MAP training rows.",
    ]
    res["runtime_s"] = round(time.time() - t0, 1)
    det.save_json(res, ROOT / "results" / "detector.json")
    print(f"wrote results/detector.json in {res['runtime_s']}s")


if __name__ == "__main__":
    main()
