"""Step 13: physics checked against analytic solutions; Predict-Observe-Explain flow (no LLM)."""
import math

import pytest
from fastapi.testclient import TestClient

from engine import api, sims
from engine.contract import SimRun, SimTurn
from engine.sims import poe
from server.main import app

G = 9.81


@pytest.mark.parametrize("h", [1.0, 20.0, 120.0])
@pytest.mark.parametrize("m", [0.1, 1.0, 30.0])
def test_free_fall_no_drag_matches_analytic_and_ignores_mass(h, m):
    r = sims.run("free_fall", {"mass_kg": m, "height_m": h})["result"]
    assert r["time_to_ground_s"] == pytest.approx(math.sqrt(2 * h / G), rel=1e-3)
    assert r["impact_speed_m_s"] == pytest.approx(math.sqrt(2 * G * h), rel=1e-3)  # energy: v^2 = 2 g h


def test_free_fall_with_drag_heavier_lands_first():
    light = sims.run("free_fall", {"mass_kg": 1, "height_m": 50, "air_drag": True})["result"]["time_to_ground_s"]
    heavy = sims.run("free_fall", {"mass_kg": 10, "height_m": 50, "air_drag": True})["result"]["time_to_ground_s"]
    assert heavy < light and light > math.sqrt(2 * 50 / G)


@pytest.mark.parametrize("L", [0.25, 1.0, 3.0])
def test_pendulum_small_angle_period_and_energy(L):
    a = sims.run("pendulum", {"length_m": L, "mass_kg": 0.1, "amplitude_deg": 3, "duration_s": 30})["result"]
    b = sims.run("pendulum", {"length_m": L, "mass_kg": 15, "amplitude_deg": 3, "duration_s": 30})["result"]
    assert a["period_s"] == pytest.approx(2 * math.pi * math.sqrt(L / G), rel=1e-3)
    assert a["period_s"] == b["period_s"]                       # mass does not matter
    assert a["energy_drift_rel"] < 1e-5                         # no damping: energy conserved


def test_pendulum_large_angle_is_slower():
    big = sims.run("pendulum", {"length_m": 1, "amplitude_deg": 60, "duration_s": 20})["result"]
    assert big["period_s"] > big["small_angle_period_s"] * 1.05  # nonlinear equation, not the small-angle formula


def test_cart_newton_second_law_and_friction():
    r = sims.run("cart_force", {"mass_kg": 2, "force_n": 4, "push_s": 2, "friction_mu": 0, "duration_s": 6})["result"]
    assert r["speed_end_of_push_m_s"] == pytest.approx(4 * 2 / 2, rel=1e-6)   # v = F t / m
    assert r["speed_at_end_m_s"] == pytest.approx(4.0, rel=1e-6)              # no force, no friction: constant
    assert r["distance_m"] == pytest.approx(0.5 * 2 * 2 ** 2 + 4 * 4, rel=1e-4)
    f = sims.run("cart_force", {"mass_kg": 2, "force_n": 4, "push_s": 2, "friction_mu": 0.1, "duration_s": 8})["result"]
    v = (4 / 2 - 0.1 * G) * 2
    assert f["speed_end_of_push_m_s"] == pytest.approx(v, rel=1e-4)
    assert f["stop_time_s"] == pytest.approx(2 + v / (0.1 * G), rel=1e-3) and f["speed_at_end_m_s"] == 0
    stuck = sims.run("cart_force", {"mass_kg": 10, "force_n": 5, "push_s": 3, "friction_mu": 0.5})["result"]
    assert stuck["distance_m"] == 0 and stuck["speed_end_of_push_m_s"] == 0      # push below static friction


def test_parameters_are_validated():
    with pytest.raises(ValueError):
        api.sim_run("free_fall", {"mass_kg": -1})
    with pytest.raises(ValueError):
        api.sim_run("free_fall", {"height_m": 10_000})
    with pytest.raises(ValueError):
        api.sim_run("rocket", {})                               # not whitelisted
    with pytest.raises(ValueError):
        api.sim_run("pendulum", {"length_m": 1, "colour": "red"})  # unknown parameter
    SimRun.model_validate(api.sim_run("pendulum", {"length_m": 2}))
    sch = api.sim_templates()
    assert sch["free_fall"]["properties"]["mass_kg"]["maximum"] == 50


def test_bank_correct_answers_are_computed():
    its = poe.items()
    assert len(its) == 8
    for i in its.values():
        assert sum(o["outcome"] == i["observed"] for o in i["options"].values()) == 1
        assert "correct" not in poe._raw()["items"][0]                # never stored by hand
    assert its["S1"]["observed"] == "same" and its["S4"]["observed"] == "constant_speed"
    assert its["S4T"]["observed"] == "slows_and_stops"


def test_poe_flow_updates_physics_posterior(monkeypatch):
    monkeypatch.setitem(api.cfg()["live"], "allow_unverified_dev", True)
    sid = api.start_session({"name": "T", "lang": "fr"})["session_id"]
    views = api.sim_items(sid)
    assert {v["id"] for v in views} == {"S1", "S2", "S3", "S4"}
    assert "correct" not in views[0] and views[0]["text"].startswith("Deux boules")
    with pytest.raises(ValueError):
        api.sim_predict(sid, "S1", "A", None)                    # confidence tap required
    t = api.sim_predict(sid, "S1", "A", "sure")                  # "heavier first" = P1
    SimTurn.model_validate(t)
    assert t["grading"]["method"] == "simulation" and t["grading"]["correct"] is False
    assert t["observed"] == "same" and len(t["runs"]) == 2 and t["expects"] == "explanation"
    m1 = {h["id"]: h["prob"] for h in t["posterior"]}
    assert max(m1, key=m1.get) == "M1"
    assert t["result_text"]["lang"] == "fr" and t["result_text"]["shown_allowed"]
    e = api.sim_explain(sid, "S1", "les deux tombent pareil")
    assert e["expects"] == "transfer_answer" and e["next_item"]["id"] == "S1T"
    tt = api.sim_predict(sid, "S1T", "B", "sure")
    assert tt["grading"]["correct"] is True and tt["stage"] == "transfer_result" and tt["expects"] == "none"
    # the maths posterior is untouched
    assert all(abs(h["prob"] - 0.2) < 1e-9 for h in api.get_state(sid)["posterior"])


def test_sims_over_http(monkeypatch):
    monkeypatch.setitem(api.cfg()["live"], "allow_unverified_dev", True)
    c = TestClient(app)
    assert c.post("/api/v1/sims/run", json={"template": "free_fall", "params": {"mass_kg": 999}}).status_code == 400
    r = c.post("/api/v1/sims/run", json={"template": "cart_force", "params": {}}).json()
    assert r["result"]["speed_at_end_m_s"] == 4.0
    sid = c.post("/api/v1/sessions", json={"student": {"name": "T", "lang": "ar"}}).json()["session_id"]
    items = c.get(f"/api/v1/sessions/{sid}/sims").json()
    assert items and items[0]["text"]
    t = c.post(f"/api/v1/sessions/{sid}/sims/S2/predict", json={"option": "C", "confidence": "unsure"}).json()
    assert t["grading"]["correct"] is True and t["result_text"]["lang"] == "ar"
