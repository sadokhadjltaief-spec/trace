"""Maths programme by level (data/curriculum/tunisie_maths.json, built by scripts/make_curriculum.py).

The file is an INDICATIVE reference written by the TRACE team, not the official Ministry of Education document; the
response carries its status and disclaimer so the UI shows them. No LLM, works offline.
"""
from __future__ import annotations

import json
from functools import lru_cache

from engine import ROOT
from engine.contract import Curriculum

FILE = ROOT / "data" / "curriculum" / "tunisie_maths.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def get(level: str | None = None) -> dict:
    d = _data()
    levels = d["levels"]
    chosen = None
    if level:
        chosen = next((lv for lv in levels if lv["id"] == level), None)
        if chosen is None:
            raise KeyError(level)
    return Curriculum(subject=d["subject"], status=d["status"], disclaimer=d["disclaimer"], domains=d["domains"],
                      levels=[{**lv, "chapters": []} for lv in levels], level=chosen).model_dump()
