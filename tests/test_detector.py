import numpy as np
import pytest

from engine import ROOT, detector as det

HAS_MAP = (ROOT / "data" / "raw" / "map" / "train.csv").exists()


@pytest.mark.parametrize("text,lang", [
    ("because 1+2 is 3 and 3+5 is 8", "en"),
    ("j'ai additionné les numérateurs et les dénominateurs", "fr"),
    ("جمعت البسط مع البسط والمقام مع المقام", "ar"),
    ("5ater 3malt 1+2 w 3+5 ya3ni 3/8", "darija"),
])
def test_detect_language(text, lang):
    assert det.detect_language(text) == lang


def test_rank_to_dist():
    d = det.rank_to_dist(["M2", "other", "M0"])
    assert abs(d.sum() - 1) < 1e-12
    assert d.argmax() == det.LABELS.index("M2")
    assert d[det.LABELS.index("other")] > d[det.LABELS.index("M1")]
    flat = det.rank_to_dist(["nonsense"])
    assert np.allclose(flat, 1 / len(det.LABELS))


def test_map_label():
    assert det.map_label({"Misconception": "Additive"}) == "M4"
    assert det.map_label({"Misconception": "Tacking"}) == "other"
    assert det.map_label({"Misconception": float("nan")}) == "M0"  # pandas NaN is a float, not a label
    assert det.map_label({"Misconception": None}) == "M0"


@pytest.mark.skipif(not HAS_MAP, reason="MAP data is local-only")
def test_tfidf_detects_additive_explanation():
    q = {"text": r"\( \frac{A}{10}=\frac{9}{15} \) What is the value of \( A \) ?", "map_question_id": 31778,
         "options": {"A": r"\( 3 \)", "B": r"\( 4 \)", "C": r"\( 6 \)", "D": r"\( 9 \)"}, "correct": "C"}
    r = det.detect(q, "B", "10 to 15 is adding 5 so I took 5 away from 9", use_llm=False)
    assert r["method"] == "tfidf"
    assert max(r["dist"], key=r["dist"].get) == "M4"
    # right answer, additive reasoning (the 'right answer, wrong reasoning' case)
    r2 = det.detect(q, "C", "15 take away 5 is 10 so 9 take away 3 is 6", use_llm=False)
    assert abs(sum(r2["dist"].values()) - 1) < 1e-9
