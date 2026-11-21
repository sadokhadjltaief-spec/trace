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
                     "(trace_notes/cours_fractions_relatifs.pdf p.1).", school=False, judge_ok=True,
         tutor_text="Pour l'aire d'un rectangle, on multiplie la longueur par la largeur : 3 × 4 = 12."):
    def f(system, user, *, purpose, **kw):
        if purpose == "chat_tutor":
            return {"answer": tutor_text}
        if purpose == "chat_tutor_judge":
            return {"texts": [{"id": "a", "congruent": [], "claims": []}]}
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


@pytest.mark.parametrize("q,expr,val", [("5*8", "5 × 8", "40"), ("combien font 12/4 ?", "12 / 4", "3"),
                                        ("(-8) - (-5)", "(-8) - (-5)", "-3"), ("كم يساوي 7*6؟", "7 × 6", "42")])
def test_arithmetic_is_computed_exactly_without_llm(courses, monkeypatch, q, expr, val):
    def no_llm(*a, **k):
        raise AssertionError("no LLM call for arithmetic")
    monkeypatch.setattr(llm, "ask_json", no_llm)
    r = api.ask(q, "fr")
    assert r["method"] == "computed" and r["answer"]["text"] == f"{expr} = {val}" and "SymPy" in r["label"]


def test_school_question_not_in_courses_gets_a_labelled_tutor_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "COURSES", tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    rag.index(root=tmp_path / "empty", use_embeddings=False)
    monkeypatch.setattr(llm, "ask_json", fake())
    r = api.ask("Comment calculer l'aire d'un rectangle ?", "fr")
    assert r["method"] == "tutor_llm" and r["answer"]["shown_allowed"] and "pas tirée de ton cours" in r["label"]
    monkeypatch.setattr(llm, "ask_json", fake(tutor_text="Donc 3 × 4 = 13."))          # false maths: not shown
    r = api.ask("Comment calculer l'aire d'un rectangle ?", "fr")
    assert r["method"] == "not_found" and "hors ligne" in r["answer"]["text"]


def test_chat_http(courses, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", fake(school=False))
    c = TestClient(app)
    r = c.post("/api/v1/chat", json={"question": "football ?", "lang": "en"}).json()
    assert r["method"] == "refusal" and r["answer"]["lang"] == "en"
    assert c.post("/api/v1/chat", json={"question": "  ", "lang": "fr"}).status_code == 400


def test_off_topic_is_refused_even_when_a_course_page_looks_similar(courses, monkeypatch):
    # regression: "Qui est Cristiano Ronaldo ?" got a page from a physics PDF and was answered from it
    monkeypatch.setattr(rag.Index, "search", lambda self, q, k=None: [
        {**self.chunks[0].__dict__, "score": 0.1, "bm25": 0.0, "cosine": 0.86, "relevant": True}])
    monkeypatch.setattr(llm, "ask_json", fake(school=False))
    r = api.ask("Qui est Cristiano Ronaldo ?", "fr")
    assert r["method"] == "refusal" and not r["citations"]


def test_passages_that_do_not_cover_the_question_go_to_the_tutor(courses, monkeypatch):
    base = fake()

    def f(system, user, *, purpose, **kw):
        if purpose == "chat_answer":
            return {"covered": False, "answer": ""}
        return base(system, user, purpose=purpose, **kw)
    monkeypatch.setattr(llm, "ask_json", f)
    r = api.ask("Explique les fractions et le théorème de Pythagore", "fr")
    assert r["method"] == "tutor_llm" and "pas tirée de ton cours" in r["label"]
