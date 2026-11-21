"""Demo moment: same RIGHT answer, different reasoning -> different diagnosis. Offline (demo mode, 0 tokens).

Two students answer Q11 (A/10 = 9/15, correct answer C = 6) with the right option and "sure".
Their free-text "Why?" differs: one reasons additively (misconception M4), one multiplicatively (correct).
In demo mode the LLM part of the detector is not called (cache miss -> TF-IDF only, trained on real MAP data),
so this runs without network. The posterior update is engine/bayes.py (tau-tempered explanation evidence).

Usage: .\\.venv\\Scripts\\python.exe scripts\\demo_right_answer.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import api, llm  # noqa: E402

CASES = [("Student A", "because 10 + 5 = 15 so you do 9 - 3 = 6"),
         ("Student B", "I divided 15 by 5 and 10 by 5, so 3 times 2 is 6")]


def main():
    for who, why in CASES:
        s = api.start_session({"name": who, "lang": "en"}, demo=True)
        before = {h["id"]: h["prob"] for h in s["posterior"]}
        t = api.submit_answer(s["session_id"], "Q11", "C", "sure", explanation=why)
        after = {h["id"]: h["prob"] for h in t["posterior"]}
        ev = t["explanation_evidence"]
        top = max(ev["dist"], key=lambda d: d["prob"])
        print(f"\n{who}: chose C (correct: {t['grading']['correct']}), sure. Why: \"{why}\"")
        print(f"  explanation detector ({ev['method']}): {top['id']} {top['prob']:.2f}")
        print("  posterior M0..M4 before: " + "  ".join(f"{k} {v:.2f}" for k, v in before.items()))
        print("  posterior M0..M4 after:  " + "  ".join(f"{k} {v:.2f}" for k, v in after.items()))
    llm.set_demo_mode(False)


if __name__ == "__main__":
    main()
