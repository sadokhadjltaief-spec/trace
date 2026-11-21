"""Load config.yaml + .env once."""
from __future__ import annotations

import os
from functools import lru_cache

import yaml
from dotenv import load_dotenv

from engine import ROOT


@lru_cache(maxsize=1)
def cfg() -> dict:
    load_dotenv(ROOT / ".env")  # never overrides variables already set in the system env
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, default: str | None = None) -> str | None:
    cfg()
    return os.getenv(name) or default
