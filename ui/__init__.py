"""Frontend display helpers (STUB, owned by the frontend). Enforces docs/INTERFACE.md rules 1, 4 and 5.

Imports from the engine: only engine.api / engine.api_fake.
"""
from __future__ import annotations

import re

import streamlit as st

from engine import api, api_fake


def backend():
    """Real engine or fake fixtures, chosen in the sidebar."""
    return api_fake if st.session_state.get("data_source", "engine") == "fake fixtures" else api


def sidebar():
    with st.sidebar:
        st.radio("Data", ["engine", "fake fixtures"], key="data_source",
                 help="'fake fixtures' = docs/fixtures/*.json (FAKE numbers, for building pages).")
        st.caption("STUB pages: the teammate replaces them, keeping docs/INTERFACE.md.")


def latex_to_md(s: str) -> str:
    return re.sub(r"\\\((.*?)\\\)", lambda m: f"${m.group(1).strip()}$", s, flags=re.S)


def show_text(safe: dict, where=None) -> bool:
    """Render a SafeText only if the engine allowed it (guards + style linter ran and passed)."""
    where = where or st
    if not safe or not safe.get("shown_allowed"):
        failed = [c["name"] for c in (safe or {}).get("checks", []) if c["status"] == "fail"]
        where.warning(f"Text withheld: guards did not pass ({', '.join(failed) or 'not checked'}).")
        return False
    where.markdown(latex_to_md(safe["text"]))
    return True


def show_warnings(state: dict):
    for w in state.get("warnings", []):
        st.warning(w)
