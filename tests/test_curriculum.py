"""Curriculum reference (no LLM)."""
from fastapi.testclient import TestClient

from engine import api
from engine.contract import Curriculum
from server.main import app


def test_levels_and_chapters():
    r = api.curriculum()
    Curriculum.model_validate(r)
    ids = [lv["id"] for lv in r["levels"]]
    assert {"7e", "8e", "9e", "bac-m", "bac-se"} <= set(ids) and len(ids) == len(set(ids))
    assert r["status"] == "indicative" and "officiel" in r["disclaimer"]["fr"] and r["level"] is None
    nine = api.curriculum("9e")["level"]
    assert any("Thalès" in c["title"]["fr"] for c in nine["chapters"])
    for lv in [api.curriculum(i)["level"] for i in ids]:
        assert lv["chapters"], lv["id"]
        for c in lv["chapters"]:
            assert c["domain"] in r["domains"] and all(c["title"][k] for k in ("fr", "ar", "en"))


def test_http():
    c = TestClient(app)
    assert c.get("/api/v1/curriculum?level=bac-se").json()["level"]["name"]["fr"].startswith("Bac Sciences")
    assert c.get("/api/v1/curriculum?level=nope").status_code == 404
