import math

import numpy as np
import pytest

from engine import bayes
from engine.bayes import H, Diagnoser, build_table, entropy


def synth_bank():
    """3 questions per misconception, one mapped distractor each (no MAP data)."""
    qs, n = [], 0
    for m in ["M1", "M2", "M3", "M4"]:
        for k in range(3):
            n += 1
            qs.append({"id": f"S{n}", "options": {"A": "a", "B": "b", "C": "c", "D": "d"}, "correct": "A",
                       "option_misconception": {"B": m, "C": None, "D": None}})
    return qs


@pytest.fixture
def table():
    return build_table(synth_bank())


def test_rows_normalised(table):
    for q in table.L.values():
        for row in q.values():
            assert abs(sum(row.values()) - 1) < 1e-9
            assert min(row.values()) > 0


def test_posterior_sums_to_one(table):
    d = Diagnoser(table)
    assert abs(d.posterior.sum() - 1) < 1e-12
    d.observe_answer("S1", "B", "sure")
    d.observe_explanation({"M1": 0.7, "M0": 0.1, "other": 0.2})
    assert abs(d.posterior.sum() - 1) < 1e-12


def test_uniform_entropy():
    assert math.isclose(entropy(np.full(5, 0.2)), math.log2(5))


def test_non_discriminating_question_has_zero_ig(table):
    flat = {"id": "F", "options": {"A": "1", "B": "2"}, "correct": "A", "option_misconception": {}}
    t = build_table(synth_bank() + [flat])
    for h in H:  # make every hypothesis answer identically
        t.L["F"][h] = {"A": 0.5, "B": 0.5}
    assert abs(Diagnoser(t).expected_ig("F")) < 1e-12
    assert Diagnoser(t).expected_ig("S1") > 0.05


def test_hit_increases_target(table):
    d = Diagnoser(table)
    d.observe_answer("S4", "B")  # S4 targets M2
    assert d.top()[0] == "M2"


def test_confidence_tap():
    t = build_table(synth_bank())
    plain, sure, unsure = Diagnoser(t), Diagnoser(t), Diagnoser(t)
    plain.observe_answer("S1", "B")
    sure.observe_answer("S1", "B", "sure")
    unsure.observe_answer("S1", "B", "unsure")
    assert sure.as_dict()["M1"] > plain.as_dict()["M1"] > unsure.as_dict()["M1"]
    assert sure.as_dict()["M0"] < plain.as_dict()["M0"]
    fr = Diagnoser(t)
    fr.observe_answer("S1", "A", "unsure")
    assert fr.fragile == ["S1"]


def test_explanation_tempered(table):
    d = Diagnoser(table)
    d.observe_explanation({"M3": 0.99, "M0": 0.0025, "M1": 0.0025, "M2": 0.0025, "M4": 0.0025})
    # tau=0.5 keeps one explanation from dominating: still below the stop threshold
    assert d.top()[0] == "M3" and d.top()[1] < 0.85


def test_scripted_m3_student_diagnosed_in_most_runs(table):
    rng = np.random.default_rng(0)
    correct = 0
    runs = 200
    for _ in range(runs):
        d = Diagnoser(table)
        while not d.done():
            qid = d.next_question()["question"]
            if qid is None:
                break
            opts = list(table.questions[qid]["options"])
            row = table.L[qid]["M3"]
            d.observe_answer(qid, rng.choice(opts, p=[row[a] for a in opts]))
        correct += d.top()[0] == "M3"
    assert correct / runs > 0.7


def test_next_question_returns_top3(table):
    nq = Diagnoser(table).next_question()
    assert nq["question"] and len(nq["alternatives"]) == 2
    assert nq["ig_bits"] >= nq["alternatives"][0]["ig_bits"] >= nq["alternatives"][1]["ig_bits"]


def test_stop_rules(table):
    d = Diagnoser(table, p=bayes.params(max_questions=2))
    d.observe_answer("S1", "A")
    d.observe_answer("S2", "A")
    assert d.done() and d.next_question()["stop"]


def test_map_data_rows_replace_defaults():
    q = {"id": "Q", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "correct": "A",
         "option_misconception": {"B": "M1"},
         "map_label_answer_counts": {"M1": {"B": 98, "A": 2}, "M0": {"A": 90, "C": 10}}}
    t = build_table([q])
    assert t.source["Q"]["M1"] == "map_data" and t.source["Q"]["M2"] == "default"
    assert abs(t.L["Q"]["M1"]["B"] - 99 / 104) < 1e-12  # add-one smoothing
