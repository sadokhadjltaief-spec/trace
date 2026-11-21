"""Tests never write into the real call / guard log (.cache/trace.db): each test gets a temporary database."""
import sqlite3

import pytest

from engine import llm

_real_db = llm._db


@pytest.fixture(autouse=True)
def _tmp_log_db(monkeypatch, tmp_path):
    path = tmp_path / "trace_test.db"

    def db():
        con = sqlite3.connect(path, timeout=30)
        con.execute("""CREATE TABLE IF NOT EXISTS llm_calls(
            ts REAL, session TEXT, purpose TEXT, model TEXT, cached INTEGER,
            prompt_tokens INTEGER, completion_tokens INTEGER, latency_s REAL, attempts INTEGER, error TEXT)""")
        return con
    monkeypatch.setattr(llm, "_db", db)
