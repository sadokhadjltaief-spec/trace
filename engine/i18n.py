"""Fixed strings in FR / AR / EN (i18n/tutor.json). Code-written text only; the LLM never fills these."""
from __future__ import annotations

import functools
import json

from engine import ROOT

LANGS = ("fr", "ar", "en")


@functools.lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads((ROOT / "i18n" / "tutor.json").read_text(encoding="utf-8"))


def t(key: str, lang: str = "en", **kw) -> str:
    row = _table()[key]
    s = row.get(lang) or row["en"]
    return s.format(**kw) if kw else s


def lang_of(lang: str | None) -> str:
    return lang if lang in LANGS else "en"


@functools.lru_cache(maxsize=1)
def _bank_tr() -> dict:
    """data/bank/bank_i18n.json (local-only, like bank.json): FR/AR question stems and worked solutions."""
    p = ROOT / "data" / "bank" / "bank_i18n.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"questions": {}, "reconstruction": {}}


def question(q: dict, lang: str) -> tuple[str, dict]:
    """(text, options) of a bank question in `lang`; falls back to the bank's English."""
    tr = _bank_tr()["questions"].get(q["id"], {}).get(lang)
    return (tr["text"], tr["options"]) if tr and lang != "en" else (q["text"], q["options"])


def reconstruction(r: dict, lang: str) -> tuple[str, list[str]]:
    tr = _bank_tr()["reconstruction"].get(r["id"], {}).get(lang)
    return (tr["problem"], tr["steps"]) if tr and lang != "en" else (r["problem"], r["worked_solution"])
