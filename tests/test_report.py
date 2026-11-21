"""Step 15: trilingual report (Markdown + PDF + calibration chart), translated evidence and handoff note."""
import pymupdf
import pytest
from fastapi.testclient import TestClient

from engine import ROOT, api, guards, llm
from engine import studio as studio_pkg
from engine.contract import ReportExport, SessionSummary
from server.main import app

HAS = (ROOT / "data" / "bank" / "bank.json").exists() and (ROOT / "assets" / "fonts" / "NotoSans.ttf").exists()
pytestmark = pytest.mark.skipif(not HAS, reason="bank / fonts are local-only")


def fake(system, user, *, purpose, **kw):
    if purpose == "guard_judge":
        return {"reveals_answer": False, "congruent": {}, "claims": []}
    if purpose == "tutor_diagnosis":
        return {"error": "e", "faulty_step": "s", "correct_idea": "i"}
    if purpose.startswith("tutor_hint"):
        msg = {"French": "Regarde les dénominateurs. Que représentent-ils ?", "Arabic": "انظر إلى المقامات. ماذا تعني؟"}
        return {"message": next((v for k, v in msg.items() if k in system), "Look at the bottom numbers.")}
    if purpose == "tutor_recon_rubric":
        return {"verdict": "correct", "reason": "r"}
    raise llm.LLMError(purpose)


def _session(lang, monkeypatch, tmp_path, handoff=False):
    monkeypatch.setattr(llm, "ask_json", fake)
    monkeypatch.setattr(studio_pkg, "EXPORTS", tmp_path / "exports")
    sid = api.start_session({"name": "Amira", "level": "7e", "lang": lang}, detector_llm=False)["session_id"]
    s = api._SESSIONS[sid]
    for _ in range(10):
        q = api.get_state(sid)["current_question"]
        bq = s["by_id"][q["id"]]
        opt = next((o for o, m in bq.get("option_misconception", {}).items() if m == "M1"),
                   next(o for o in bq["options"] if o != bq["correct"]))
        t = api.submit_answer(sid, q["id"], opt, "sure")
        if t["state"] != "DIAGNOSE":
            break
    t = api.tutor_reply(sid, choice=s["by_id"][t["question"]["id"]]["correct"])
    for _ in range(12):
        if t["state"] == "RECONSTRUCT":
            t = api.tutor_reply(sid, choice=str(s["recon"]["error_step"]), text="x")
        elif t["state"] == "TRANSFER":
            q = s["by_id"][t["question"]["id"]]
            t = api.tutor_reply(sid, choice=next(o for o in q["options"] if o != q["correct"]) if handoff else q["correct"])
        elif t["state"].startswith("HINT"):
            t = api.tutor_reply(sid, choice=s["by_id"][t["question"]["id"]]["correct"])
        else:
            break
    return sid, t


@pytest.mark.parametrize("lang,heading", [("fr", "Rapport TRACE"), ("en", "TRACE report"), ("ar", "TRACE")])
def test_report_files_in_three_languages(lang, heading, monkeypatch, tmp_path):
    sid, t = _session("fr", monkeypatch, tmp_path)
    assert t["state"] == "DONE"
    r = api.report(sid, lang)
    ReportExport.model_validate(r)
    names = {f["path"].rsplit("/", 1)[-1] for f in r["files"]}
    assert names == {f"report_{lang}.md", f"report_{lang}.pdf", "calibration.png"}
    md = open(next(f["path"] for f in r["files"] if f["path"].endswith(".md")), encoding="utf-8").read()
    assert heading in md and "calibration.png" in md
    pdf = pymupdf.open(next(f["path"] for f in r["files"] if f["path"].endswith(".pdf")))
    assert pdf.page_count >= 1 and len(pdf[0].get_text()) > 200
    summ = api.summary(sid, lang)
    SessionSummary.model_validate(summ)
    if lang != "en":
        for e in summ["evidence"]:
            assert guards.language_check(e.split(";")[0], lang) is None or lang == "fr", e
    if lang == "ar":
        assert all("اختار" in e or "محاولة" in e or "إيجاد" in e or "سؤال" in e for e in summ["evidence"])


def test_handoff_note_translated(monkeypatch, tmp_path):
    sid, t = _session("fr", monkeypatch, tmp_path, handoff=True)
    assert t["state"] == "HANDOFF"
    fr = api.summary(sid, "fr")["handoff_note"]
    assert fr["shown_allowed"] and fr["text"].startswith("Erreur type probable") and len(fr["text"].splitlines()) == 3
    ar = api.summary(sid, "ar")["handoff_note"]
    assert ar["lang"] == "ar" and guards.language_check(ar["text"], "ar") is None
    md = open(next(f["path"] for f in api.report(sid, "fr")["files"] if f["path"].endswith(".md")), encoding="utf-8").read()
    assert "Note pour l'enseignant" in md


def test_report_http(monkeypatch, tmp_path):
    sid, _ = _session("en", monkeypatch, tmp_path)
    c = TestClient(app)
    r = c.post(f"/api/v1/sessions/{sid}/report", params={"lang": "fr"})
    assert r.status_code == 200 and r.json()["lang"] == "fr"
    assert c.get(f"/api/v1/sessions/{sid}/summary", params={"lang": "ar"}).json()["outcome"]["lang"] == "ar"
