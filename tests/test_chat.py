"""Course chat ("Ask the tutor"): RAG answers with citations, off-topic refusal, fail-closed, extractive fallback."""
import shutil

import pytest
from fastapi.testclient import TestClient

from engine import ROOT, api, llm, rag
from engine.contract import ChatAnswer
from server.main import app

NOTES = ROOT / "data" / "courses" / "trace_notes" / "cours_fractions_relatifs.pdf"
pytestmark = pytest.mark.skipif(not NOTES.exists(), reason="run scripts/make_course_notes.py")


@pytest.fixture
def courses(tmp_path, monkeypatch):
    root = tmp_path / "courses"
    (root / "trace_notes").mkdir(parents=True)
    shutil.copy(NOTES, root / "trace_notes" / NOTES.name)
    monkeypatch.setattr(rag, "COURSES", root)
    monkeypatch.setattr(rag, "CACHE", tmp_path / "cache")
    rag.index(root=root, use_embeddings=False)
    return root


def fake(answer_text="Pour additionner, on prend un dénominateur commun : 1/3 + 2/5 = 11/15 "
                     "(trace_notes/cours_fractions_relatifs.pdf p.1).", school=False, judge_ok=True):
    def f(system, user, *, purpose, **kw):
        if purpose == "chat_topic":
            if not judge_ok:
                raise llm.CacheMiss("demo")
            return {"school": school}
        if purpose == "chat_answer":
            return {"answer": answer_text}
        if purpose == "chat_answer_judge":
            return {"texts": [{"id": "a", "congruent": [], "claims": []}]}
        raise llm.LLMError(purpose)
    return f


def test_math_question_answered_with_citations(courses, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", fake())
    r = api.ask("Comment additionner deux fractions ?", "fr")
    ChatAnswer.model_validate(r)
    assert r["on_topic"] and r["method"] == "rag_llm" and r["answer"]["shown_allowed"]
    assert r["citations"] and r["citations"][0]["page"] == 1 and "p.1" in r["answer"]["text"]


@pytest.mark.parametrize("q", ["Qui a gagné le match de football hier ?", "Raconte-moi une blague"])
def test_off_topic_refused_politely(courses, monkeypatch, q):
    monkeypatch.setattr(llm, "ask_json", fake(school=False))
    r = api.ask(q, "fr")
    assert not r["on_topic"] and r["method"] == "refusal" and not r["citations"]
    assert r["answer"]["text"] == "Je suis un tuteur éducatif, je ne peux répondre qu'aux questions sur tes cours."


def test_refuses_when_topic_judge_unavailable(courses, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", fake(judge_ok=False))
    r = api.ask("Parle-moi de ta journée", "ar")
    assert r["method"] == "refusal" and r["answer"]["lang"] == "ar"


def test_false_maths_in_answer_falls_back_to_the_course_text(courses, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", fake(answer_text="On fait 1/3 + 2/5 = 3/8 (trace_notes/cours_fractions_relatifs.pdf p.1)."))
    r = api.ask("Comment additionner deux fractions ?", "fr")
    assert r["method"] == "rag_extractive" and r["answer"]["text"].startswith("Voici ce que dit ton cours")
    assert "3/8 (" not in r["answer"]["text"].split("\n")[0]


def test_school_question_not_in_courses_is_not_answered_from_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "COURSES", tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    rag.index(root=tmp_path / "empty", use_embeddings=False)
    monkeypatch.setattr(llm, "ask_json", fake())
    r = api.ask("Comment calculer le volume d'une sphère ?", "fr")
    assert r["on_topic"] and r["method"] == "not_found" and "ne réponds pas de mémoire" in r["answer"]["text"]


def test_chat_http(courses, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", fake(school=False))
    c = TestClient(app)
    r = c.post("/api/v1/chat", json={"question": "football ?", "lang": "en"}).json()
    assert r["method"] == "refusal" and r["answer"]["lang"] == "en"
    assert c.post("/api/v1/chat", json={"question": "  ", "lang": "fr"}).status_code == 400
