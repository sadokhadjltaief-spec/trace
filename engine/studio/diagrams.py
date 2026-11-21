"""Diagrams drawn by code (matplotlib), never by an image model: the maths in them is exact.
One diagram per misconception, contrasting the wrong idea with the correct one."""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TEAL, GREY, RED = "#0f766e", "#cbd5e1", "#b91c1c"
LABELS = {
    "en": {"wrong": "wrong idea", "right": "correct", "M1": "1/3 + 2/5", "M3": "(-8) - (-5)"},
    "fr": {"wrong": "idée fausse", "right": "correct", "M1": "1/3 + 2/5", "M3": "(-8) - (-5)"},
    "ar": {"wrong": "wrong idea", "right": "correct", "M1": "1/3 + 2/5", "M3": "(-8) - (-5)"},  # Latin in images
}


def _bars(ax, rows: list[tuple[str, Fraction, str]]):
    for i, (label, f, colour) in enumerate(rows):
        y = len(rows) - 1 - i
        n, d = f.numerator, f.denominator
        whole = int(n // d)
        for k in range(max(whole, 0)):
            ax.barh(y, 1, left=k, color=colour, edgecolor="white")
        rem = Fraction(n, d) - whole
        if rem:
            for k in range(rem.denominator):
                ax.barh(y, 1 / rem.denominator, left=whole + k / rem.denominator,
                        color=colour if k < rem.numerator else GREY, edgecolor="white")
        ax.text(-0.05, y, label, ha="right", va="center", fontsize=11)
    ax.set_yticks([])
    ax.set_xlim(0, max(1, max(float(f) for _, f, _ in rows)) + 0.05)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)


def draw(misconception: str, path: Path, lang: str = "en") -> Path:
    L = LABELS.get(lang, LABELS["en"])
    fig, ax = plt.subplots(figsize=(7, 2.8), dpi=150)
    if misconception == "M1":   # adding tops and bottoms gives a sum smaller than one of the parts
        _bars(ax, [("1/3", Fraction(1, 3), TEAL), ("2/5", Fraction(2, 5), TEAL),
                   (f"3/8 ({L['wrong']})", Fraction(3, 8), RED), (f"11/15 ({L['right']})", Fraction(11, 15), TEAL)])
        ax.set_title("1/3 + 2/5", fontsize=12)
    elif misconception == "M2":  # multiplying a fraction by a whole number: only the numerator
        _bars(ax, [("2/3", Fraction(2, 3), TEAL), (f"10/15 ({L['wrong']})", Fraction(10, 15), RED),
                   (f"10/3 ({L['right']})", Fraction(10, 3), TEAL)])
        ax.set_title("2/3 × 5", fontsize=12)
    elif misconception == "M3":  # number line: (-8) - (-5) = -3
        ax.axhline(0, color="black", lw=1)
        for x in range(-10, 11):
            ax.plot([x, x], [-0.08, 0.08], color="black", lw=0.8)
            if x % 2 == 0:
                ax.text(x, -0.3, str(x), ha="center", fontsize=9)
        ax.annotate("", xy=(-3, 0.35), xytext=(-8, 0.35), arrowprops=dict(arrowstyle="->", color=TEAL, lw=2))
        ax.text(-5.5, 0.5, f"-(-5) = +5  →  -3 ({L['right']})", ha="center", color=TEAL)
        ax.plot([3], [0], "o", color=RED)
        ax.text(3, 0.35, f"3 ({L['wrong']})", ha="center", color=RED)
        ax.set_ylim(-0.6, 0.9)
        ax.axis("off")
        ax.set_title("(-8) - (-5)", fontsize=12)
    elif misconception == "M4":  # equivalent fractions: multiply, do not add
        _bars(ax, [("9/15", Fraction(9, 15), TEAL), (f"6/10 ({L['right']})", Fraction(6, 10), TEAL),
                   (f"4/10 ({L['wrong']})", Fraction(4, 10), RED)])
        ax.set_title("A/10 = 9/15", fontsize=12)
    else:
        plt.close(fig)
        raise ValueError(f"no diagram for {misconception}")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path
