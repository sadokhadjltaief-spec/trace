"""Same functions as engine/api.py, returning FAKE data from docs/fixtures/ (for building the frontend).

Shapes are identical to the real API (validated by tests/test_contract.py). Never show these numbers as results.
"""
from __future__ import annotations

import copy
import json

from engine import ROOT
from engine.api import list_results, misconceptions, read_results  # real, read-only  # noqa: F401

_FX = ROOT / "docs" / "fixtures"


def _fx(name: str, sid: str | None = None) -> dict:
    d = copy.deepcopy(json.loads((_FX / f"{name}.json").read_text(encoding="utf-8")))
    if sid:
        d["session_id"] = sid
    return d


def start_session(student: dict, profile: dict | None = None, demo: bool = False) -> dict:
    d = _fx("session_state")
    d["student"].update({k: v for k, v in student.items() if k in ("name", "level", "lang")})
    d["profile"] = dict(profile or {})
    return d


def get_state(session_id: str) -> dict:
    return _fx("session_state", session_id)


def next_question(session_id: str) -> dict:
    return _fx("next_question")


def submit_answer(session_id: str, question_id: str, option: str, confidence: str | None,
                  explanation: str | None = None) -> dict:
    if confidence not in ("sure", "unsure"):
        raise ValueError("confidence tap is required: 'sure' or 'unsure'")
    return _fx("tutor_turn", session_id)


def tutor_reply(session_id: str, text: str | None = None, choice: str | None = None) -> dict:
    return _fx("tutor_turn_reconstruct", session_id)


def summary(session_id: str) -> dict:
    return _fx("session_summary", session_id)


def studio_generate(session_id: str, tool: str, source: dict) -> dict:
    if source.get("folder_allow_derivatives") is False:
        return _fx("studio_output_refused", session_id)
    d = _fx("studio_output", session_id)
    d["tool"] = tool
    return d
