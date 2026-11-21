"""Deterministic maths helpers (SymPy). Used by the bank builder, guards and grading.

No LaTeX parser dependency: we convert the small LaTeX subset found in MAP/Eedi items
(\\frac, mixed numbers, \\times, \\div, unicode minus) to SymPy syntax ourselves.
"""
from __future__ import annotations

import re

import sympy as sp

_MIXED = re.compile(r"(?<![\d/])(\d+)\s+(\d+)\s*/\s*(\d+)")  # "3 1/3" -> (3+1/3)


def latex_to_plain(s: str) -> str:
    t = str(s)
    t = t.replace("\\(", " ").replace("\\)", " ").replace("$", " ")
    for _ in range(3):  # nested fracs
        t = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = t.replace("\\times", "*").replace("\\div", "/").replace("\\cdot", "*")
    t = t.replace("×", "*").replace("÷", "/").replace("−", "-").replace("–", "-")
    t = t.replace("\\left", "").replace("\\right", "").replace("\\square", "?")
    t = re.sub(r"\\[a-zA-Z]+", " ", t)
    t = t.replace("{", "(").replace("}", ")")
    # (9)/(12) -> 9/12 ; (-8)-(-5) -> -8--5 ; but keep 2(3) and f(x) untouched
    t = re.sub(r"(?<![\w)])\(\s*(-?\d+(?:\.\d+)?)\s*\)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def _mixed_to_sum(t: str) -> str:
    # "(3) (1)/(3)" or "3 1/3" -> "(3+1/3)"
    t = re.sub(r"\((\d+)\)\s*\((\d+)\)/\((\d+)\)", r"(\1+\2/\3)", t)
    t = re.sub(r"(?<![\d)])(\d+)\s+\((\d+)\)/\((\d+)\)", r"(\1+\2/\3)", t)
    return _MIXED.sub(r"(\1+\2/\3)", t)


def to_sympy(s: str):
    """Parse a numeric/algebraic expression; returns a SymPy object or None."""
    t = _mixed_to_sum(latex_to_plain(s))
    if not t or "?" in t:
        return None
    t = re.sub(r"(?<=\d)\s*(?=[a-z(])", "*", t)  # 2x -> 2*x, 2(x) -> 2*(x)
    t = re.sub(r"(?<=\))\s*(?=[\d(a-z])", "*", t)
    try:
        return sp.nsimplify(sp.sympify(t, rational=True), rational=True)
    except Exception:  # noqa: BLE001
        return None


def value(s: str):
    """Exact value (Rational/expr) or None."""
    e = to_sympy(s)
    if e is None:
        return None
    try:
        return sp.simplify(e)
    except Exception:  # noqa: BLE001
        return None


def equal(a: str, b: str) -> bool | None:
    va, vb = value(a), value(b)
    if va is None or vb is None:
        return None
    try:
        return bool(sp.simplify(va - vb) == 0)
    except Exception:  # noqa: BLE001
        return None


# expressions made of numbers, fractions, + - * / ( ) and a few letters
_EXPR = r"[-+]?\(?\s*-?\d+(?:\.\d+)?(?:\s*(?:/|\*|×|÷|\+|-|−)\s*\(?\s*-?\d+(?:\.\d+)?\s*\)?)*\s*\)?"
# not glued to letters/slashes on either side (skip 'A/10 = 9/15', 'x = 3')
_EQ = re.compile(rf"(?<![\w/.])({_EXPR})\s*=\s*({_EXPR})(?![\w/])")
_NUM_TOKEN = re.compile(r"-?\d+(?:\s+\d+/\d+|\s*/\s*\d+|\.\d+)?")


def check_equalities(text: str) -> list[dict]:
    """Find simple 'lhs = rhs' claims in free text and verify each with SymPy."""
    out = []
    t = latex_to_plain(text)
    # chains like 1+2 = 3 = 3: check consecutive pairs
    for m in _EQ.finditer(t):
        prev = t[:m.start()].rstrip().split(" ")[-1] if t[:m.start()].strip() else ""
        if prev and (prev[-1] in "*/+-×÷−=" or (len(prev) == 1 and prev.isalpha())):
            continue  # lhs is the tail of a longer expression we cannot see whole (e.g. 'A x 15 = ...')
        lhs, rhs = m.group(1).strip(), m.group(2).strip()
        ok = equal(lhs, rhs)
        out.append({"claim": f"{lhs} = {rhs}", "ok": ok})
    return out


def numeric_tokens(text: str) -> list[str]:
    return [m.group(0).strip() for m in _NUM_TOKEN.finditer(latex_to_plain(text))]


def mentions_value(text: str, target: str, exclude_from: str = "") -> list[str]:
    """Tokens in `text` whose value equals `target`, ignoring tokens that literally appear in `exclude_from`."""
    tv = value(target)
    if tv is None:
        return []
    excl = set(numeric_tokens(exclude_from)) if exclude_from else set()
    hits = []
    for tok in numeric_tokens(text):
        if tok in excl:
            continue
        v = value(tok)
        if v is not None and sp.simplify(v - tv) == 0:
            hits.append(tok)
    return hits
