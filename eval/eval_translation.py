"""Does the detector survive French / Arabic / Tunisian Darija input? -> results/translation.json

1. 100 held-out MAP rows (same 80/20 split and seed as eval_detector.py) with fixed label quotas
   (12 each M1..M4, 30 M0, 22 other).
2. Each explanation is translated by the LLM (LLM_MODEL) into French, Modern Standard Arabic and Tunisian Darija
   (Latin script "Arabizi"). These are SYNTHETIC stand-ins for Tunisian student writing.
3. The detector pipeline runs on them: deterministic language detection -> LLM translation back to English
   (EVAL_MODEL, batched) -> TF-IDF detector (trained on the 80 % split).
4. Reported: TF-IDF metrics on the English originals vs each language, the drop, language-detection accuracy,
   and TF-IDF on the raw (untranslated) text to show why the translation step is needed.
Free tier: items are batched (10 per call): ~30 calls on LLM_MODEL + ~30 on EVAL_MODEL.

Usage: .\\.venv\\Scripts\\python.exe eval\\eval_translation.py
"""
from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

import collections

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, detector as det, llm  # noqa: E402
from eval_detector import SEED, metrics  # noqa: E402

N = 100
BATCH = 10
LANGS = {"fr": "French (as a Tunisian middle-school student would write it)",
         "ar": "Modern Standard Arabic (Arabic script)",
         "darija": "Tunisian Darija in Latin script (Arabizi: 3 = ع, 7 = ح, 9 = ق, 5 = خ)"}

FWD_SYS = """Translate each student's maths explanation into {lang}.
Keep the student's style, spelling level and mistakes in reasoning; keep every number and operation.
Return JSON: {{"items": [{{"id": "...", "text": "..."}}, ...]}}"""

BACK_SYS = """Translate each short maths explanation into plain English. Inputs may be French, Modern Standard
Arabic or Tunisian Darija (Arabic script, or Latin script where 3 = ع, 7 = ح, 9 = ق, 5 = خ). Keep the maths exactly
as written, including mistakes; do not correct the reasoning.
Return JSON: {"items": [{"id": "...", "english": "..."}, ...]}"""


def batched(items, sysmsg, key, model, purpose, extra_user=""):
    out = {}
    for i in range(0, len(items), BATCH):
        ch = items[i:i + BATCH]
        user = extra_user + "\n".join(f"[{it['id']}] {it['text']}" for it in ch)
        try:
            d = llm.ask_json(sysmsg, user, purpose=purpose, model=model, max_tokens=3000)
            for it in (d or {}).get("items", []):
                if isinstance(it, dict) and it.get("id") is not None:
                    out[str(it["id"]).strip("[]")] = str(it.get(key, ""))
        except Exception as e:  # noqa: BLE001
            print(f"  {purpose}: batch failed: {type(e).__name__}: {str(e)[:120]}")
    return out


def main():
    t0 = time.time()
    df = det.load_map()
    train, test = train_test_split(df, test_size=0.2, random_state=SEED, stratify=df.label)
    # fixed label quotas so the rare misconception labels are present (proportional sampling would give ~1 M1 row)
    quota = {"M1": 12, "M2": 12, "M3": 12, "M4": 12, "M0": 30, "other": 22}
    sample = pd.concat([test[test.label == lab].sample(q, random_state=SEED) for lab, q in quota.items()]) \
        .sample(frac=1, random_state=SEED)
    model = det.train_tfidf(train)
    items = [{"id": str(r.row_id), "text": r.StudentExplanation} for r in sample.itertuples()]

    def score(texts: dict[str, str]):
        rows = [det.features(r.QuestionId, r.MC_Answer, r.is_correct, texts.get(str(r.row_id), ""))
                for r in sample.itertuples()]
        return metrics(list(sample.label), det.proba(model, det.frame(rows)), sample.Category)

    eng = {it["id"]: it["text"] for it in items}
    res = {"script": "eval/eval_translation.py",
           "label": "SYNTHETIC translations of real MAP explanations (not real Tunisian student text)",
           "created": dt.datetime.now().isoformat(timespec="seconds"), "seed": SEED, "n": len(sample),
           "composition": sample.label.value_counts().to_dict(),
           "forward_model": llm.default_model(), "back_model": llm.eval_model(), "detector": "tfidf",
           "english_original": score(eng), "languages": {}}
    for lang, desc in LANGS.items():
        fwd = batched(items, FWD_SYS.format(lang=desc), "text", llm.default_model(), f"eval_translation_fwd_{lang}")
        detected = {k: det.detect_language(v) for k, v in fwd.items()}
        back = batched([{"id": k, "text": v} for k, v in fwd.items()], BACK_SYS, "english", llm.eval_model(),
                       f"eval_translation_back_{lang}")
        m_back = score(back)
        m_raw = score(fwd)
        res["languages"][lang] = {
            "translated_items": len(fwd), "back_translated_items": len(back),
            "language_detection_accuracy": round(float(np.mean([v == lang for v in detected.values()])), 4)
            if detected else None,
            "detected_as": {k: int(v) for k, v in collections.Counter(detected.values()).items()},
            "pipeline_translate_back": m_back,
            "no_translation_raw_text": m_raw,
            "drop_vs_english": {k: round(res["english_original"][k] - m_back[k], 4)
                                for k in ("accuracy", "map_at_3", "macro_f1")},
            "examples": [{"en": eng[k], lang: fwd[k], "back": back.get(k, "")} for k in list(fwd)[:3]]}
        print(f"{lang}: detect_acc={res['languages'][lang]['language_detection_accuracy']} "
              f"acc {res['english_original']['accuracy']} -> {m_back['accuracy']} (raw {m_raw['accuracy']})")
    res["caveats"] = ["Translations are LLM-generated, not real Tunisian student writing.",
                      "Detector component measured: TF-IDF after back-translation (the LLM few-shot part was not "
                      "re-run here, to stay inside the free-tier request budget).",
                      "Arabic-script Darija is not tested separately; it goes through the 'ar' path."]
    res["runtime_s"] = round(time.time() - t0, 1)
    det.save_json(res, ROOT / "results" / "translation.json")
    print(f"wrote results/translation.json in {res['runtime_s']}s")


if __name__ == "__main__":
    main()
