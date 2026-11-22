"""Practice quiz and flashcards from the student's material (fake LLM)."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from engine import ROOT, api, llm, rag
from engine.contract import PracticeCards, PracticeQuiz
from server.main import app

NOTES = ROOT / "data" / "courses" / "trace_notes" / "cours_fractions_relatifs.pdf"
pytestmark = pytest.mark.skipif(not NOTES.exists(), reason="run scripts/make_course_notes.py")

QUIZ = {"questions": [
    {"question": "Que faut-il avant d'additionner deux fractions ?",
     "options": {"A": "Le même numérateur", "B": "Le même dénominateur", "C": "Des nombres pairs", "D": "Rien"},
     "correct": "B", "explanation": "On met les fractions au même dénominateur.",
     "source": {"file": "cours_fractions_relatifs.pdf", "page": 1}},
    {"question": "Combien vaut 2/3 × 5 ?", "options": {"A": "10/15", "B": "10/3", "C": "2/15", "D": "7/3"},
     "correct": "B", "explanation": "On multiplie seulement le numérateur : 2/3 × 5 = 10/3.",
     "source": {"file": "cours_fractions_relatifs.pdf", "page": 2}},
    {"question": "Combien vaut (-8) - (-5) ?", "options": {"A": "-3", "B": "3", "C": "-13", "D": "13"},
     "correct": "A", "explanation": "On ajoute l'opposé : (-8) - (-5) = -8 + 5 = -3.",
     "source": {"file": "cours_fractions_relatifs.pdf", "page": 3}},
    {"question": "Quelle fraction est égale à 9/15 ?", "options": {"A": "4/10", "B": "6/10", "C": "9/10", "D": "3/15"},
     "correct": "B", "explanation": "9/15 = 3/5 = 6/10.", "source": {"file": "cours_fractions_relatifs.pdf", "page": 4}},
]}
BLIND = {"answers": [{"id": "q0", "answer": "B"}, {"id": "q1", "answer": "B"}, {"id": "q2", "answer": "B"},  # q2 disagrees
                     {"id": "q3", "answer": "B"}]}


def fake(system, user, *, purpose, **kw):
    if purpose == "practice_quiz":
        return QUIZ
    if purpose == "practice_quiz_blind":
        return BLIND
    if purpose in ("practice_quiz_judge", "practice_summary_judge", "studio_flashcards_judge"):
        return {"texts": [{"id": i, "congruent": [], "claims": []} for i in re.findall(r"^\[(\w+)\]", user, re.M)]}
    if purpose == "studio_flashcards":
        return {"cards": [{"front": "Comment additionner deux fractions ?", "back": "On les met au même dénominateur."},
                          {"front": "Que vaut 1/5 + 2/5 ?", "back": "1/5 + 2/5 = 4/5."}]}   # false: dropped
    raise llm.LLMError(purpose)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "COURSES", tmp_path / "courses")
    monkeypatch.setattr(llm, "ask_json", fake)


def test_quiz_keeps_only_cross_checked_questions_and_hides_the_key(env):
    r = api.practice_quiz([(NOTES.name, NOTES.read_bytes())], lang="fr")
    PracticeQuiz.model_validate(r)
    assert len(r["questions"]) == 3 and "3 questions gardées sur 4" in r["verification"]
    assert "correct" not in json.dumps(r["questions"]) and "explanation" not in json.dumps(r["questions"])
    q = r["questions"][1]
    assert q["question"]["text"].startswith("Combien vaut 2/3") and q["sources"][0]["page"] == 2
    ok = api.practice_check(r["quiz_id"], q["id"], "B")
    bad = api.practice_check(r["quiz_id"], q["id"], "A")
    assert ok["correct"] and not bad["correct"] and bad["correct_option"] == "B"
    assert "10/3" in bad["explanation"]["text"]
    with pytest.raises(KeyError):
        api.practice_check(r["quiz_id"], "nope", "A")


def test_sources_and_pasted_text(env):
    assert api.practice_quiz(source="youtube", text="https://youtube.com/x", lang="fr")["refused"].startswith("Cette source")
    assert api.practice_quiz(lang="fr")["refused"]
    r = api.practice_quiz(text="Les fractions.\n\nPour additionner deux fractions on prend le même dénominateur.",
                          source="text", lang="fr")
    assert r["questions"] and r["questions"][0]["sources"] == []          # pasted text: no file page


def test_cards_from_file(env):
    r = api.practice_cards([(NOTES.name, NOTES.read_bytes())], lang="fr")
    PracticeCards.model_validate(r)
    assert len(r["cards"]) == 1 and "(1 retirées)" in r["note"] and r["cards"][0]["back"]["shown_allowed"]


def test_practice_http(env):
    c = TestClient(app)
    r = c.post("/api/v1/practice/quiz", files=[("files", (NOTES.name, NOTES.read_bytes(), "application/pdf"))],
               data={"lang": "fr"}).json()
    q = r["questions"][0]
    chk = c.post(f"/api/v1/practice/quiz/{r['quiz_id']}/check", json={"question_id": q["id"], "option": "B"}).json()
    assert chk["correct"]
    assert c.post(f"/api/v1/practice/quiz/{r['quiz_id']}/check", json={"question_id": "zz", "option": "B"}).status_code == 404
    cards = c.post("/api/v1/practice/cards", data={"text": "Une fraction a un numérateur et un dénominateur.", "source": "text",
                                                   "lang": "fr"}).json()
    assert "cards" in cards


SUMMARY = {"title": "Fractions et nombres relatifs",
           "overview": "Ce cours présente les opérations sur les fractions et les nombres relatifs.",
           "sections": [{"heading": "Additionner des fractions", "points": [
               {"text": "Pour additionner deux fractions, on les met au même dénominateur.",
                "source": {"file": "cours_fractions_relatifs.pdf", "page": 1}},
               {"text": "On additionne ensuite les numérateurs.", "source": {"file": "autre.pdf", "page": 9}}]},  # bad page
                        {"heading": "Soustraire des relatifs", "points": [
               {"text": "Soustraire un nombre revient à ajouter son opposé : (-8) - (-5) = -3.",
                "source": {"file": "cours_fractions_relatifs.pdf", "page": 3}}]}],
           "formulas": [{"text": "1/5 + 2/5 = 4/5", "source": {"file": "cours_fractions_relatifs.pdf", "page": 1}}],  # false
           "mistakes": [{"text": "Additionner les dénominateurs est une erreur.",
                         "source": {"file": "cours_fractions_relatifs.pdf", "page": 1}}]}


def test_summary_cites_pages_and_drops_bad_points(env, monkeypatch):
    def fake2(system, user, *, purpose, **kw):
        return SUMMARY if purpose == "practice_summary" else fake(system, user, purpose=purpose, **kw)
    monkeypatch.setattr(llm, "ask_json", fake2)
    from engine.contract import PracticeSummary
    r = api.practice_summary([(NOTES.name, NOTES.read_bytes())], focus="les fractions", pages=2, lang="fr")
    PracticeSummary.model_validate(r)
    assert not r["refused"] and r["title"]["text"].startswith("Fractions")
    assert [len(s["points"]) for s in r["sections"]] == [1, 1]              # uncited point dropped
    assert all(p["sources"] for s in r["sections"] for p in s["points"])
    assert r["formulas"] == [] and len(r["mistakes"]) == 1                  # false equality dropped by SymPy
    assert "(2 retirés)" in r["note"] and {s["page"] for s in r["sources"]} == {1, 3}
    assert api.practice_summary(source="wikipedia", text="https://x", lang="fr")["refused"]


def test_summary_http(env, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda s, u, *, purpose, **kw: SUMMARY if purpose == "practice_summary"
                        else fake(s, u, purpose=purpose, **kw))
    c = TestClient(app)
    r = c.post("/api/v1/practice/summary", data={"text": "Les fractions.\n\nOn prend le même dénominateur.",
                                                 "source": "text", "pages": "4", "lang": "fr"})
    assert r.status_code == 200 and r.json()["refused"]          # pasted text: the fake cites a PDF page, so all dropped
