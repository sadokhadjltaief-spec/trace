"""PDF writer (fpdf2) with the bundled fonts: Noto Sans (Latin) and Noto Naskh Arabic.
Arabic lines are shaped with arabic-reshaper + python-bidi and right-aligned."""
from __future__ import annotations

import re
from pathlib import Path

from engine import ROOT

FONTS = ROOT / "assets" / "fonts"
_AR = re.compile(r"[؀-ۿ]")
_GLYPHS = {"≠": "!=", "≤": "<=", "≥": ">=", "→": "->", "‑": "-", "−": "-"}


def _ar(text: str) -> str:
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


class Doc:
    def __init__(self, title: str):
        from fpdf import FPDF
        if not (FONTS / "NotoSans.ttf").exists():
            raise FileNotFoundError("fonts missing: run scripts/fetch_fonts.py")
        self.pdf = FPDF(format="A4")
        self.pdf.set_auto_page_break(True, margin=15)
        self.pdf.add_font("NotoSans", "", str(FONTS / "NotoSans.ttf"))
        self.pdf.add_font("NotoArabic", "", str(FONTS / "NotoNaskhArabic.ttf"))
        self.pdf.set_title(title)
        self.pdf.add_page()

    def page(self):
        self.pdf.add_page()

    def text(self, s: str, size: int = 11, gap: float = 2.0):
        """One paragraph. Arabic paragraphs: Arabic font, shaped, right-aligned."""
        pdf = self.pdf
        s = str(s)
        for k, v in _GLYPHS.items():  # symbols missing from the bundled fonts
            s = s.replace(k, v)
        for line in s.split("\n"):
            if _AR.search(line):
                pdf.set_font("NotoArabic", size=size + 1)
                pdf.multi_cell(0, size * 0.55, _ar(line), align="R", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.set_font("NotoSans", size=size)
                pdf.multi_cell(0, size * 0.5, line, align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    def title(self, s: str):
        self.text(s, size=16, gap=4)

    def heading(self, s: str):
        self.text(s, size=13, gap=2)

    def image(self, path: Path, w: float = 150):
        self.pdf.image(str(path), w=w)
        self.pdf.ln(3)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(path))
        return path
