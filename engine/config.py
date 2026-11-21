"""Load config.yaml + .env once."""
from __future__ import annotations

import os
from functools import lru_cache

import yaml
from dotenv import load_dotenv

from engine import ROOT


@lru_cache(maxsize=1)
def cfg() -> dict:
    # .env wins over the system environment (2026-11-21: a new GROQ_API_KEY was put in .env while an old one
    # was still set as a Windows user variable)
    load_dotenv(ROOT / ".env", override=True)
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, default: str | None = None) -> str | None:
    cfg()
    return os.getenv(name) or default
