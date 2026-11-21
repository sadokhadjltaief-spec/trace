"""Study Studio (CLAUDE.md section 12, part A): diagnosis first, then material targeted at the diagnosed
misconception. Every output says "Targeted at: <name>" when a diagnosis exists, lists its sources, passes the
guards and the active style profile, and is written to exports/<session>/. Folders with allow_derivatives: false
are refused (Najahni policy).

Tools: flashcards (LLM drafts, guarded, human review before use, Leitner review, Anki + TSV export),
summary (LLM, guarded, Markdown + PDF), quiz (verified bank only, worksheet PDF with answer key on page 2),
slides (python-pptx), pdf (summary + diagram + worksheet), diagram (matplotlib).
"""
from __future__ import annotations

from pathlib import Path

from engine import ROOT

EXPORTS = ROOT / "exports"
TOOLS = ("flashcards", "summary", "quiz", "slides", "pdf", "diagram")


def export_dir(session_id: str) -> Path:
    p = EXPORTS / session_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:  # outside the repo (tests)
        return str(p).replace("\\", "/")
