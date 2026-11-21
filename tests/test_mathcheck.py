import sympy as sp

from engine import mathcheck as mc


def test_latex_fraction_and_mixed():
    assert mc.value(r"\( \frac{11}{15} \)") == sp.Rational(11, 15)
    assert mc.value(r"\( 3 \frac{1}{3} \)") == sp.Rational(10, 3)
    assert mc.value("2 4/6") == sp.Rational(8, 3)
    assert mc.value(r"\( -13 \)") == -13


def test_equal():
    assert mc.equal(r"\frac{10}{15}", "2/3") is True
    assert mc.equal("3/8", r"\frac{11}{15}") is False
    assert mc.equal("?", "1") is None


def test_check_equalities():
    res = mc.check_equalities("We know 1/3 = 5/15 and 2/5 = 6/15, but 1+2 = 4 is wrong.")
    oks = {r["claim"]: r["ok"] for r in res}
    assert oks["1/3 = 5/15"] is True and oks["2/5 = 6/15"] is True
    assert oks["1+2 = 4"] is False


def test_equalities_with_variables_are_skipped():
    assert mc.check_equalities("Set up A/10 = 9/15 and cross-multiply.") == []
    assert mc.check_equalities("so A × 15 = 9 × 10, then divide") == []


def test_negative_parentheses():
    assert mc.value(r"\( (-8)-(-5) \)") == -3
    assert "9/12" in mc.numeric_tokens(r"\( \frac{9}{12} \)")


def test_mentions_value_ignores_question_tokens():
    assert mc.mentions_value("The answer is 11/15.", "11/15") == ["11/15"]
    assert mc.mentions_value("Look at 1/3 again.", "1/3", exclude_from="1/3 + 2/5") == []
    assert mc.mentions_value("Try 22/30.", "11/15") == ["22/30"]
