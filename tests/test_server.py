"""FastAPI layer (server/main.py): every endpoint returns the contract shapes; errors map to HTTP codes."""
import pytest
from fastapi.testclient import TestClient

from engine import ROOT, llm
from engine.contract import NextQuestion, SessionState, SessionSummary, TutorTurn
from server.main import app

HAS_BANK = (ROOT / "data" / "bank" / "bank.json").exists()
c = TestClient(app)


def _no_llm(monkeypatch):
    def f(system, user, *, purpose, **kw):
        if purpose == "guard_judge":
            return {"reveals_answer": False, "congruent": {}, "claims": []}
        if purpose == "tutor_diagnosis":
            return {"error": "e", "faulty_step": "s", "correct_idea": "i"}
        if purpose.startswith("tutor_hint"):
            return {"message": "Look at the bottom numbers. What size are the parts?"}
        if purpose == "tutor_recon_rubric":
            return {"verdict": "correct", "reason": "r"}
        raise llm.LLMError("no LLM in tests")
    monkeypatch.setattr(llm, "ask_json", f)


def test_health_and_results():
    h = c.get("/api/v1/health").json()
    assert h["ok"] and h["contract_version"]
    names = c.get("/api/v1/results").json()
    assert "diagnosis" in names
    assert c.get("/api/v1/results/diagnosis").json()["script"] == "eval/bench_diagnosis.py"
    assert c.get("/api/v1/results/..%2Fconfig").status_code in (400, 404)
    assert c.get("/api/v1/sessions/nope").status_code == 404


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_full_session_over_http(monkeypatch):
    _no_llm(monkeypatch)
    s = c.post("/api/v1/sessions", json={"student": {"name": "T", "lang": "en"}}).json()
    SessionState.model_validate(s)
    sid = s["session_id"]
    from engine import api
    by_id = api._SESSIONS[sid]["by_id"]
    NextQuestion.model_validate(c.get(f"/api/v1/sessions/{sid}/next").json())
    # missing confidence -> 422 (request validation)
    q = s["current_question"]
    assert c.post(f"/api/v1/sessions/{sid}/answer", json={"question_id": q["id"], "option": "A"}).status_code == 422
    t = None
    for _ in range(10):
        q = c.get(f"/api/v1/sessions/{sid}").json()["current_question"]
        bq = by_id[q["id"]]
        opt = next((o for o, m in bq.get("option_misconception", {}).items() if m == "M1"),
                   next(o for o in bq["options"] if o != bq["correct"]))
        t = c.post(f"/api/v1/sessions/{sid}/answer", json={"question_id": q["id"], "option": opt,
                                                           "confidence": "sure"}).json()
        TutorTurn.model_validate(t)
        if t["state"] != "DIAGNOSE":
            break
    assert t["state"] == "HINT_1"
    rq = by_id[t["question"]["id"]]
    t = c.post(f"/api/v1/sessions/{sid}/reply", json={"choice": rq["correct"]}).json()
    assert t["state"] == "RECONSTRUCT"
    step = api._SESSIONS[sid]["recon"]["error_step"]
    t = c.post(f"/api/v1/sessions/{sid}/reply", json={"choice": str(step), "text": "added the bottoms"}).json()
    assert t["state"] == "TRANSFER" and t["grading"]["method"] == "llm_rubric"
    tq = by_id[t["question"]["id"]]
    t = c.post(f"/api/v1/sessions/{sid}/reply", json={"choice": tq["correct"]}).json()
    assert t["state"] == "DONE"
    assert c.post(f"/api/v1/sessions/{sid}/reply", json={"choice": "A"}).status_code == 400
    r = c.get(f"/api/v1/sessions/{sid}/summary").json()
    SessionSummary.model_validate(r)
    assert r["status"] == "mastered"
    assert c.post(f"/api/v1/sessions/{sid}/studio", json={"tool": "video"}).status_code == 501  # not built (P2)
    assert len(c.get("/api/v1/misconceptions").json()) == 5


def test_course_endpoints(tmp_path, monkeypatch):
    from engine import rag
    monkeypatch.setattr(rag, "COURSES", tmp_path / "courses")
    monkeypatch.setattr(rag, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(rag, "embedder", lambda: None)  # BM25 only: fast
    r = c.post("/api/v1/courses/upload",
               files=[("files", ("notes.txt", "Pour additionner deux fractions, on cherche un denominateur commun.".encode(),
                                 "text/plain"))])
    assert r.status_code == 200 and r.json()["saved"] == ["notes.txt"]
    assert (tmp_path / "courses" / "uploads" / "notes.txt").exists()
    a = c.post("/api/v1/courses/search", json={"query": "additionner deux fractions"}).json()
    assert a["found"] and a["hits"][0]["file"] == "uploads/notes.txt" and a["hits"][0]["allow_derivatives"]
    bad = c.post("/api/v1/courses/upload", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
    assert bad.status_code == 400
