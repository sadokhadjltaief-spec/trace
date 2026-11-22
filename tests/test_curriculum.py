"""Curriculum reference (no LLM)."""
import pytest
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


def test_cycles_primary_college_lycee():
    r = api.curriculum()
    assert list(r["cycles"]) == ["primaire", "college", "lycee"]
    assert [lv["id"] for lv in api.curriculum(cycle="School")["levels"]] == ["1p", "2p", "3p", "4p", "5p", "6p"]
    assert [lv["id"] for lv in api.curriculum(cycle="Collège")["levels"]] == ["7e", "8e", "9e"]
    lycee = [lv["id"] for lv in api.curriculum(cycle="lycée")["levels"]]
    assert lycee[0] == "1s" and "bac-m" in lycee and "7e" not in lycee
    assert r["cycles"]["primaire"]["resource"]["url"] == "https://mourajaa.com/"
    assert r["cycles"]["college"]["resource"]["url"] == r["cycles"]["lycee"]["resource"]["url"] == "https://www.najahni.tn/"
    with pytest.raises(KeyError):
        api.curriculum(cycle="université")


def test_chapter_detail_and_plan():
    nine = api.curriculum("9e")["level"]["chapters"][0]          # Nombres réels et racines carrées
    d = api.curriculum_chapter(nine["id"])
    assert d["cycle"] == "college" and d["resource"]["name"] == "najahni.tn" and d["number"] == 1
    p1 = api.curriculum_chapter(api.curriculum("3p")["level"]["chapters"][0]["id"])
    assert p1["resource"]["name"] == "mourajaa.com" and p1["cycle_name"]["fr"] == "Primaire"
    plan = api.curriculum_chapter_plan(nine["id"], "fr")
    assert len(plan["days"]) == len(nine["notions"]) + 1
    assert all(t["shown_allowed"] for day in plan["days"] for t in [day["title"], *day["tasks"]])
    assert "najahni.tn" in plan["days"][0]["tasks"][0]["text"]
    c = TestClient(app)
    assert c.get(f"/api/v1/curriculum/chapters/{nine['id']}").status_code == 200
    assert c.post(f"/api/v1/curriculum/chapters/{nine['id']}/plan?lang=ar").json()["title"]["lang"] == "ar"
    assert c.get("/api/v1/curriculum/chapters/nope").status_code == 404
    assert c.get("/api/v1/curriculum?cycle=School").json()["cycle"] == "primaire"
