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


_OPS = {"<": lambda d: d < 0, ">": lambda d: d > 0, "<=": lambda d: d <= 0, ">=": lambda d: d >= 0}


def compare(a: str, op: str, b: str) -> bool | None:
    """Truth of 'a op b' for numeric a, b (op in < > <= >=); None if not both numeric."""
    op = {"≤": "<=", "≥": ">=", "=<": "<=", "=>": ">="}.get(op, op)
    va, vb = value(a), value(b)
    if va is None or vb is None or op not in _OPS:
        return None
    try:
        d = sp.nsimplify(va - vb)
        if not d.is_real:
            return None
        return bool(_OPS[op](d))
    except Exception:  # noqa: BLE001
        return None


# comparison words (EN / FR / AR) -> operator
_WORD_OPS = [
    (r"(?:is\s+)?(?:smaller|less|lower)\s+than", "<"), (r"(?:is\s+)?(?:bigger|greater|larger|more|higher)\s+than", ">"),
    (r"(?:est\s+)?(?:plus\s+petite?s?|inf[ée]rieure?s?)\s+(?:que|à|a)", "<"),
    (r"(?:est\s+)?(?:plus\s+grande?s?|sup[ée]rieure?s?)\s+(?:que|à|a)", ">"),
    (r"(?:هو\s+|هي\s+)?(?:أصغر|اصغر|أقل|اقل)\s+من", "<"), (r"(?:هو\s+|هي\s+)?(?:أكبر|اكبر|أكثر|اكثر)\s+من", ">"),
]
_NUM = r"-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?"
_SYM_INEQ = re.compile(rf"(?<![\w/.])({_NUM})\s*(<=|>=|≤|≥|<|>)\s*({_NUM})(?![\w/])")
_REL = r"(?:(?:qui|which|that|it|and|et|وهو|وهي|الذي|التي)\s+)?"
_WORD_INEQ = [(re.compile(rf"(?<![\w/.])({_NUM})\s*,?\s*{_REL}{w}\s+({_NUM})(?![\w/])", re.I), op)
              for w, op in _WORD_OPS]


def check_inequalities(text: str) -> list[dict]:
    """Find simple comparison claims between two numbers ('2/5 < 1/3', '2/5 est inférieur à 1/3',
    '2/5 is smaller than 1/3', 'أصغر من') and verify each with SymPy. Claims about unnamed quantities
    ('smaller than each fraction') are not visible here: the guard judge extracts those (guards.py)."""
    t = latex_to_plain(text)
    out = []
    for m in _SYM_INEQ.finditer(t):
        out.append({"claim": f"{m.group(1)} {m.group(2)} {m.group(3)}", "ok": compare(m.group(1), m.group(2), m.group(3))})
    for rx, op in _WORD_INEQ:
        for m in rx.finditer(t):
            out.append({"claim": f"{m.group(1)} {op} {m.group(2)}", "ok": compare(m.group(1), op, m.group(2))})
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
