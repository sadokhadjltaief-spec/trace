"""Maths programme by level (data/curriculum/tunisie_maths.json, built by scripts/make_curriculum.py).

The file is an INDICATIVE reference written by the TRACE team, not the official Ministry of Education document; the
response carries its status and disclaimer so the UI shows them. No LLM, works offline.
Cycles: primaire (1re-6e), college (7e-9e), lycee (1re secondaire - Bac). Each cycle names the site where the student
reads the lesson (mourajaa.com for primary, najahni.tn after): the app only links to it, it never downloads or
copies those lessons (docs/NAJAHNI_NOTE.md).
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache

from engine import ROOT
from engine.contract import ChapterDetail, Curriculum, PlanDay, StudyPlan
from engine.i18n import lang_of, t as tr

FILE = ROOT / "data" / "curriculum" / "tunisie_maths.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.strip().lower()) if not unicodedata.combining(c))


def find_cycle(text: str) -> str | None:
    """'School' / 'Primaire' -> primaire, 'Collège' -> college, 'Lycée' / 'Bac' -> lycee (None if no match)."""
    t = _fold(text or "")
    if not t:
        return None
    for cid, c in _data().get("cycles", {}).items():
        if t == cid or any(t == _fold(a) for a in c.get("aliases", [])):
            return cid
    return None


def get(level: str | None = None, cycle: str | None = None) -> dict:
    d = _data()
    levels = d["levels"]
    chosen = None
    if level:
        chosen = next((lv for lv in levels if lv["id"] == level), None)
        if chosen is None:
            raise KeyError(level)
    cid = None
    if cycle:
        cid = find_cycle(cycle)
        if cid is None:
            raise KeyError(cycle)
        levels = [lv for lv in levels if lv["cycle"] == cid]
    return Curriculum(subject=d["subject"], status=d["status"], disclaimer=d["disclaimer"], domains=d["domains"],
                      levels=[{**lv, "chapters": []} for lv in levels], level=chosen,
                      cycles=d.get("cycles", {}), cycle=cid).model_dump()


def chapter(chapter_id: str) -> dict:
    d = _data()
    for lv in d["levels"]:
        for i, ch in enumerate(lv["chapters"], 1):
            if ch["id"] == chapter_id:
                cy = d["cycles"][lv["cycle"]]
                return ChapterDetail(chapter=ch, number=i, level_id=lv["id"], level_name=lv["name"], cycle=lv["cycle"],
                                     cycle_name=cy["name"], domain_name=d["domains"][ch["domain"]],
                                     resource=cy["resource"], disclaimer=d["disclaimer"]).model_dump()
    raise KeyError(chapter_id)


def chapter_plan(chapter_id: str, lang: str = "fr") -> dict:
    """Study plan for one chapter, built by code (no LLM, works offline): one day per key notion, then a review day.
    Tasks point to the lesson on the cycle's site; nothing here claims to come from a teacher."""
    from engine import safetext
    lang = lang_of(lang)
    c = chapter(chapter_id)
    ch, site = c["chapter"], c["resource"]["name"]
    title = ch["title"].get(lang) or ch["title"]["fr"]

    def st(x: str):
        return safetext.static(x, lang=lang, style_kwargs={"max_words_per_sentence": 40, "max_questions": 3,
                                                           "neutral": True})
    notions = ch["notions"] or [title]
    days = []
    for i, n in enumerate(notions, 1):
        days.append(PlanDay(day=i, title=st(tr("chplan_day", lang, notion=n)),
                            goals=[st(tr("chplan_goal", lang, notion=n))],
                            tasks=[st(tr("chplan_read", lang, notion=n, site=site)), st(tr("chplan_examples", lang)),
                                   st(tr("chplan_exercises", lang)), st(tr("chplan_explain", lang, notion=n))],
                            sources=[], duration_min=30))
    days.append(PlanDay(day=len(days) + 1, title=st(tr("chplan_review_day", lang, chapter=title)), goals=[],
                        tasks=[st(tr("chplan_review_sheet", lang)), st(tr("chplan_review_cards", lang)),
                               st(tr("chplan_review_quiz", lang))], sources=[], duration_min=40))
    return StudyPlan(plan_id=f"chapter-{chapter_id}", title=st(tr("chplan_title", lang, chapter=title)),
                     summary=st(tr("chplan_summary", lang, n=len(days), site=site)), days=days,
                     check_questions=[], sources=[]).model_dump()
