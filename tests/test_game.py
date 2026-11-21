"""Step 14: "Chasse aux erreurs" (deterministic, no LLM)."""
import pytest
from fastapi.testclient import TestClient

from engine import ROOT, api, bayes
from engine.contract import GameTurn
from server.main import app

HAS_BANK = (ROOT / "data" / "bank" / "bank.json").exists()
pytestmark = pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")


def _correct(sid):
    g = api._SESSIONS[sid]["game"]
    rd = g["rounds"][g["i"]]
    reason = next(k for k, m in rd["reasons"].items() if m == rd["item"]["misconception"])
    return rd["item"]["error_step"], reason, rd


def test_full_game_points_streak_and_language():
    sid = api.start_session({"name": "T", "lang": "fr"})["session_id"]
    t = api.game_start(sid)
    GameTurn.model_validate(t)
    assert t["round"]["round"] == 1 and t["round"]["total"] == 5 and len(t["round"]["reasons"]) == 3
    assert "error_step" not in t["round"] and t["message"]["lang"] == "fr"
    assert t["round"]["problem"].startswith(("Additionne", "Calcule", "Écris"))   # FR bank translation
    seen = set()
    for k in range(5):
        step, reason, rd = _correct(sid)
        assert sorted(rd["reasons"].values()).count(rd["item"]["misconception"]) == 1
        seen.add(rd["item"]["id"])
        t = api.game_answer(sid, step, reason)
        assert t["feedback"]["step_ok"] and t["feedback"]["reason_ok"] and t["streak"] == k + 1
    assert t["done"] and t["round"] is None and t["points"] == 5 * 15 and t["best_streak"] == 5
    assert len(seen) == 5
    with pytest.raises(ValueError):
        api.game_answer(sid, 1, "A")


def test_wrong_reason_is_evidence_for_that_misconception():
    sid = api.start_session({"name": "T", "lang": "en"})["session_id"]
    api.game_start(sid)
    step, _, rd = _correct(sid)
    wrong_letter, wrong_m = next((k, m) for k, m in rd["reasons"].items() if m != rd["item"]["misconception"])
    before = api._SESSIONS[sid]["diag"].as_dict()[wrong_m]
    t = api.game_answer(sid, step, wrong_letter)
    after = {h["id"]: h["prob"] for h in t["posterior"]}[wrong_m]
    assert after > before and t["feedback"]["reason_ok"] is False and t["streak"] == 0
    assert t["feedback"]["points_gained"] == 10 and f"line {rd['item']['error_step']}" in t["message"]["text"]


def test_diagnosed_misconception_comes_first():
    from engine import game
    g = game.new_game(bayes.load_bank(), first="M3")
    assert g["rounds"][0]["item"]["misconception"] == "M3"


def test_game_over_http():
    c = TestClient(app)
    sid = c.post("/api/v1/sessions", json={"student": {"name": "T", "lang": "ar"}}).json()["session_id"]
    t = c.post(f"/api/v1/sessions/{sid}/game").json()
    assert t["message"]["lang"] == "ar" and t["round"]["steps"]
    assert c.post(f"/api/v1/sessions/{sid}/game/answer", json={"step": 99, "reason": "A"}).status_code == 400
