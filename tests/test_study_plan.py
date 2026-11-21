"""Study plan from an uploaded PDF (fake LLM): pages cited must exist, guards drop unsafe items, cache-friendly."""
import pymupdf
import pytest
from fastapi.testclient import TestClient

from engine import ROOT, api, llm, rag
from engine.contract import StudyPlan
from server.main import app

NOTES = ROOT / "data" / "courses" / "trace_notes" / "cours_fractions_relatifs.pdf"
pytestmark = pytest.mark.skipif(not NOTES.exists(), reason="run scripts/make_course_notes.py")

PLAN = {"title": "Plan : fractions et nombres relatifs", "summary": "Quatre jours pour revoir le cours.",
        "days": [
            {"day": 1, "title": "Additionner des fractions", "goals": ["Comprendre le dénominateur commun."],
             "tasks": ["Relis la page 1.", "Refais l'exemple : 1/3 + 2/5 = 11/15."],
             "pages": [{"file": "cours_fractions_relatifs.pdf", "page": 1}, {"file": "cours_fractions_relatifs.pdf", "page": 99}]},
            {"day": 2, "title": "Multiplier par un entier", "goals": ["Multiplier seulement le numérateur."],
             "tasks": ["Calcule 2/3 × 5 = 10/15."],          # FALSE: must be dropped by the SymPy check
             "pages": [{"file": "mauvais_nom.pdf", "page": 2}]},  # wrong file name: repaired from the page number
        ],
        "check_questions": ["Pourquoi ne peut-on pas additionner les dénominateurs ?"]}


def fake(system, user, *, purpose, **kw):
    if purpose == "study_plan":
        return PLAN
    if purpose == "study_plan_judge":
        import re
        return {"texts": [{"id": i, "congruent": [], "claims": []} for i in re.findall(r"^\[(\w+)\]", user, re.M)]}
    raise llm.LLMError(purpose)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "COURSES", tmp_path / "courses")
    monkeypatch.setattr(llm, "ask_json", fake)
    return tmp_path


def test_plan_from_pdf(env):
    r = api.study_plan([(NOTES.name, NOTES.read_bytes())], "Je veux réviser en 4 jours.", "fr")
    StudyPlan.model_validate(r)
    assert r["title"]["shown_allowed"] and len(r["sources"]) == 4
    assert (env / "courses" / "uploads" / NOTES.name).exists()            # saved as the student's own material
    d1, d2 = r["days"]
    assert [(s["file"], s["page"]) for s in d1["sources"]] == [(NOTES.name, 1)]   # page 99 removed
    assert [(s["file"], s["page"]) for s in d2["sources"]] == [(NOTES.name, 2)]   # wrong name repaired
    assert len(d1["tasks"]) == 2 and d2["tasks"] == []                    # the false task is dropped
    assert r["dropped_by_guards"] == 1 and r["check_questions"][0]["shown_allowed"]
    assert r["targeted_at"] is None


def test_plan_targets_the_diagnosis(env):
    sid = api.start_session({"name": "T", "lang": "fr"})["session_id"]
    api._SESSIONS[sid]["target"] = "M1"
    r = api.study_plan([(NOTES.name, NOTES.read_bytes())], "", "fr", sid)
    assert r["targeted_at"]["id"] == "M1"


def test_refuses_bad_or_empty_files(env, tmp_path):
    with pytest.raises(ValueError):
        api.study_plan([("virus.exe", b"MZ")], "", "fr")
    blank = pymupdf.open()
    blank.new_page()
    r = api.study_plan([("vide.pdf", blank.tobytes())], "", "fr")
    assert r["refused"] and not r["days"]


def test_study_plan_http(env):
    c = TestClient(app)
    r = c.post("/api/v1/study-plan", files=[("files", (NOTES.name, NOTES.read_bytes(), "application/pdf"))],
               data={"details": "", "lang": "fr"})
    assert r.status_code == 200 and r.json()["days"]


def test_offline_fallback_plan(env, monkeypatch):
    def miss(*a, **k):
        raise llm.CacheMiss("not cached (demo mode)")
    monkeypatch.setattr(llm, "ask_json", miss)
    r = api.study_plan([(NOTES.name, NOTES.read_bytes())], "", "fr")
    StudyPlan.model_validate(r)
    assert r["plan_id"] == "fallback" and len(r["days"]) == 4 and not r["refused"]
    assert r["days"][0]["title"]["text"].startswith("Chapitre 1") and r["days"][0]["sources"][0]["page"] == 1
    assert all(t["shown_allowed"] for d in r["days"] for t in d["tasks"])
