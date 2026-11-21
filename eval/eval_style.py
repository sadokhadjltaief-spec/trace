"""Clear and structured mode: style compliance per rule, with vs without the profile -> results/style.json

For N tutor hints per condition (same questions, levels and languages in both), the LLM writes the hint with
(a) the default profile and (b) the "clear_structured" preset in the prompt. Each RAW hint (before any guard or
regeneration) is checked by the deterministic linter against the clear-mode limits, rule by rule.
This measures how well the prompt alone follows the rules; in the live tutor the linter then blocks and
regenerates non-compliant text, and the fixed_template layout is added by code (100 % by construction).
Small on purpose (Groq free tier: 200k tokens/day per model); the brief's 100 messages did not fit today.
It measures wording compliance only. It says nothing about learning outcomes for autistic students.

Usage: .\\.venv\\Scripts\\python.exe eval\\eval_style.py [--n 10]
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, bayes, guards, llm, style, tutor  # noqa: E402
from engine.detector import save_json  # noqa: E402

CLEAR = style.preset("clear_structured")
RULES = {
    "max_15_words_per_sentence": dict(max_words_per_sentence=15),
    "at_most_one_question": dict(max_questions=1),
    "no_idioms": dict(literal=True),
    "no_praise": dict(no_praise=True),
    "no_exclamation": dict(neutral=True),
}


def wilson(k: int, n: int, z: float = 1.96):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def check(text: str, lang: str) -> dict:
    out = {}
    for name, kw in RULES.items():
        base = dict(max_words_per_sentence=10_000, neutral=False, max_questions=None, lang=lang,
                    literal=False, no_praise=False)
        base.update(kw)
        out[name] = not style.lint(text, **base)
    out["no_emoji_no_caps"] = not style.lint(text, max_words_per_sentence=10_000, neutral=False, lang=lang)
    out["right_language"] = guards.language_check(text, lang) is None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    t0 = time.time()
    llm.set_session("eval_style")
    bank = bayes.load_bank()
    mis = {m["id"]: m for m in bank["misconceptions"]}
    qs = [q for q in bank["questions"] if q.get("verified") and q["target"] in mis]
    plan = [(qs[i % len(qs)], 1 + i % 3, ("fr", "ar", "en")[i % 3]) for i in range(a.n)]
    rows = []
    for cond, profile in (("default", {}), ("clear_structured", {"preset": "clear_structured"})):
        kw_base = tutor.style_kwargs(profile)
        for q, level, lang in plan:
            m = mis[q["target"]]
            diag = {"error": f"The student shows this misconception: {m['name_en']}.",
                    "faulty_step": m.get("description", ""), "correct_idea": ""}
            try:
                text = tutor.write_hint(level, q, diag, m, lang, {**kw_base, "lang": lang}, profile=profile)
            except Exception as e:  # noqa: BLE001
                rows.append({"condition": cond, "question": q["id"], "level": level, "lang": lang,
                             "error": f"{type(e).__name__}: {str(e)[:120]}"})
                continue
            rows.append({"condition": cond, "question": q["id"], "level": level, "lang": lang, "text": text,
                         "checks": check(text, lang)})
            print(cond, q["id"], level, lang, "ok" if all(rows[-1]["checks"].values()) else
                  [k for k, v in rows[-1]["checks"].items() if not v], flush=True)
    summary = {}
    for cond in ("default", "clear_structured"):
        ok = [r for r in rows if r["condition"] == cond and "checks" in r]
        summary[cond] = {"n": len(ok)}
        for rule in [*RULES, "no_emoji_no_caps", "right_language"]:
            k = sum(r["checks"][rule] for r in ok)
            summary[cond][rule] = {"compliance": round(k / len(ok), 4) if ok else None, "ci95": wilson(k, len(ok))}
        k = sum(all(r["checks"].values()) for r in ok)
        summary[cond]["all_rules"] = {"compliance": round(k / len(ok), 4) if ok else None, "ci95": wilson(k, len(ok))}
    res = {"script": "eval/eval_style.py",
           "label": "Wording compliance of RAW LLM hints (before guards) against clear-mode rules; small sample",
           "created": dt.datetime.now().isoformat(timespec="seconds"), "model": llm.default_model(),
           "n_per_condition": a.n, "clear_profile": CLEAR, "summary": summary,
           "errors": [r for r in rows if "error" in r], "rows": [r for r in rows if "checks" in r],
           "caveats": ["Raw prompt compliance only; the live linter blocks and regenerates non-compliant text.",
                       "fixed_template (Situation / Your task / What happens next) is added by code, not measured here.",
                       "The idiom and praise lists are short hand-made lists (EN/FR/AR), not exhaustive.",
                       "Measures wording, not learning; nothing here is tested with autistic students."],
           "runtime_s": round(time.time() - t0, 1)}
    save_json(res, ROOT / "results" / "style.json")
    for cond, sm in summary.items():
        print(cond, {k: (v["compliance"] if isinstance(v, dict) else v) for k, v in sm.items()})
    print(f"wrote results/style.json in {res['runtime_s']}s")


if __name__ == "__main__":
    main()
