import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import build_bank as bb  # noqa: E402

BANK = ROOT / "data" / "bank" / "bank.json"


def test_recon_checker_catches_true_error_step_and_wrong_answer():
    bad = {"steps": [{"math": "2/3 + 1/4 = 8/12 + 3/12"}, {"math": "(8+3)/(12+12) = 11/24"}],
           "error_step": 2, "correct_answer": "11/12"}
    assert bb.blocking(bb.check_recon(bad))  # error step written as a TRUE internal working
    good = {"steps": [{"math": "2/3 + 1/4 = 8/12 + 3/12"}, {"math": "8/12 + 3/12 = 11/24"}],
            "error_step": 2, "correct_answer": "11/12"}
    assert not bb.blocking(bb.check_recon(good))
    wrong_key = dict(good, correct_answer="11/24")
    assert bb.blocking(bb.check_recon(wrong_key))
    after_false = {"steps": [{"math": "3/5 = 6/8"}, {"math": "6/8 = 12/20"}], "error_step": 1,
                   "correct_answer": "3/5"}
    assert bb.blocking(bb.check_recon(after_false))


def test_hint_checker():
    q = {"text": r"\( \frac{1}{3}+\frac{2}{5}= \)", "options": {"A": "3/8", "D": r"\( \frac{11}{15} \)"},
         "correct": "D"}
    assert not bb.check_hints(q, ["Look at the bottoms.", "Try 1/2 + 1/2.", "Use 15 as the denominator."])
    assert any("answer" in f["msg"] for f in bb.check_hints(q, ["a", "b", "It is 11/15."]))
    assert bb.blocking(bb.check_hints(q, ["a", "b", "Pick answer D."]))
    assert bb.blocking(bb.check_hints(q, ["a", "b", "Note 1/3 = 6/15."]))


@pytest.mark.skipif(not BANK.exists(), reason="bank.json is local-only; run eval/build_bank.py")
def test_bank_schema():
    b = json.loads(BANK.read_text(encoding="utf-8"))
    mids = {m["id"] for m in b["misconceptions"]}
    assert mids == {"M1", "M2", "M3", "M4"}
    assert 12 <= len(b["questions"]) <= 15
    for q in b["questions"]:
        assert q["correct"] in q["options"]
        assert q["correct"] not in q["option_misconception"]
        assert set(v for v in q["option_misconception"].values() if v) <= mids
        assert q["target"] in q["option_misconception"].values(), q["id"]
        assert len(q["verified_hints"]) == 3
    for t in b["transfer"]:
        assert len(t["question_ids"]) >= 3  # 1 diagnosis + 2 transfer loops
    assert len(b["reconstruction"]) >= 4
