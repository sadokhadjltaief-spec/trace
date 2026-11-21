"""Step 12: Study Studio with a fake LLM (no network)."""
import zipfile

import pytest

from engine import ROOT, api, llm, rag
from engine import studio as studio_pkg
from engine.contract import StudioOutput

HAS_BANK = (ROOT / "data" / "bank" / "bank.json").exists()
HAS_FONTS = (ROOT / "assets" / "fonts" / "NotoSans.ttf").exists()
pytestmark = pytest.mark.skipif(not (HAS_BANK and HAS_FONTS), reason="bank / fonts are local-only")

CARDS = {"fr": [{"front": "Combien font 1/2 + 1/4 ?", "back": "On écrit 1/2 = 2/4. Donc 1/2 + 1/4 = 3/4."},
                {"front": "Que vaut 1/3 + 1/3 ?", "back": "1/3 + 1/3 = 2/3. On garde le dénominateur."},
                {"front": "Vrai ou faux : 1/2 + 1/2 = 2/4 ?", "back": "Faux. 1/2 + 1/2 = 1."},
                {"front": "Additionne 1/5 et 2/5.", "back": "1/5 + 2/5 = 4/5."}]}   # last one is FALSE (3/5)
SHEET = {"key_idea": "Pour additionner deux fractions, on les écrit avec le même dénominateur.",
         "common_mistake": "On additionne les numérateurs et les dénominateurs. Cela donne 1/2 + 1/2 = 2/4, ce qui est faux.",
         "example": "1/2 + 1/3 = 3/6 + 2/6 = 5/6.", "formulas": ["a/c + b/c = (a+b)/c"]}


def fake(system, user, *, purpose, **kw):
    if purpose == "studio_flashcards":
        return {"cards": CARDS["fr"]}
    if purpose == "studio_summary":
        return SHEET
    if purpose.endswith("_judge"):  # judge: extract claims (SymPy decides), nothing congruent
        import re
        ids = re.findall(r"^\[(\w+)\]", user, re.M)
        return {"texts": [{"id": i, "congruent": [], "claims": []} for i in ids]}
    raise llm.LLMError(purpose)


@pytest.fixture
def sid(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "ask_json", fake)
    monkeypatch.setattr(studio_pkg, "EXPORTS", tmp_path / "exports")
    sid = api.start_session({"name": "T", "lang": "fr"})["session_id"]
    api._SESSIONS[sid]["target"] = "M1"   # as after a diagnosis
    return sid


def test_flashcards_guarded_reviewed_exported(sid):
    r = api.studio_generate(sid, "flashcards", {"kind": "diagnosis"})
    StudioOutput.model_validate(r)
    assert r["targeted_at"]["id"] == "M1" and r["sources"]
    cards = [i for i in r["items"] if "front" in i]
    assert len(cards) == 3 and {"dropped_by_guards": 1} in r["items"]       # 1/5 + 2/5 = 4/5 dropped by SymPy
    assert all(c["front"]["shown_allowed"] and not c["verified"] for c in cards)
    paths = {f["path"].rsplit("/", 1)[-1] for f in r["files"]}
    assert paths == {"flashcards.apkg", "flashcards.tsv"}
    apkg = next(f["path"] for f in r["files"] if f["path"].endswith(".apkg"))
    assert zipfile.is_zipfile(apkg)
    # human review: unverified cards cannot be reviewed
    cid = cards[0]["id"]
    with pytest.raises(ValueError):
        api.studio_card_review(sid, cid, "good")
    api.studio_card_verify(cid, True)
    api.studio_card_verify(cards[1]["id"], False)
    deck = api.studio_cards(sid, verified_only=True)
    assert [c["id"] for c in deck] == [cid]
    g = api.studio_card_review(sid, cid, "good")
    assert g["box"] == 2 and not g["lapse"]
    before = api._SESSIONS[sid]["diag"].as_dict()["M1"]
    a = api.studio_card_review(sid, cid, "again")
    after = {p["id"]: p["prob"] for p in a["posterior"]}["M1"]
    assert a["box"] == 1 and a["lapse"] and after > before                     # lapse = evidence for M1


@pytest.mark.parametrize("tool,files", [("summary", {"summary.md", "summary.pdf"}), ("pdf", {"summary.md", "trace_sheet.pdf"}),
                                        ("slides", {"slides.pptx"}), ("quiz", {"worksheet.pdf"}),
                                        ("diagram", {"diagram_M1.png"})])
def test_tools_write_files(sid, tool, files):
    r = api.studio_generate(sid, tool, {"kind": "diagnosis"})
    StudioOutput.model_validate(r)
    assert r["targeted_at"]["name_en"] and not r["refused"]
    assert {f["path"].rsplit("/", 1)[-1] for f in r["files"]} == files
    if tool == "summary":
        md = next(f["path"] for f in r["files"] if f["path"].endswith(".md"))
        text = open(md, encoding="utf-8").read()
        assert "Ciblé sur" in text and "## Sources" in text
        assert all(i["text"]["shown_allowed"] for i in r["items"])
    if tool == "slides":
        from pptx import Presentation
        prs = Presentation(next(f["path"] for f in r["files"]))
        assert 6 <= len(prs.slides) <= 10
    if tool == "quiz":
        import pymupdf
        doc = pymupdf.open(next(f["path"] for f in r["files"]))
        assert doc.page_count >= 2 and "Corrigé" in doc[doc.page_count - 1].get_text()
        assert all(set(i) == {"question_id", "text", "options"} for i in r["items"])   # no answer key in items


def test_arabic_slides_are_right_to_left(sid):
    api._SESSIONS[sid]["student"]["lang"] = "ar"
    r = api.studio_generate(sid, "slides", {"kind": "diagnosis"})
    from pptx import Presentation
    prs = Presentation(r["files"][0]["path"])
    xml = prs.slides[0].shapes[1].text_frame.paragraphs[0]._p.xml
    assert 'rtl="1"' in xml and "موجّه إلى" in prs.slides[0].shapes[1].text_frame.text


def test_refuses_najahni_and_needs_a_diagnosis(sid, monkeypatch, tmp_path):
    root = tmp_path / "courses"
    (root / "najahni").mkdir(parents=True)
    (root / "najahni" / "meta.yaml").write_text("allow_derivatives: false\n", encoding="utf-8")
    (root / "najahni" / "lecon.txt").write_text("Pour additionner deux fractions il faut un dénominateur commun.",
                                                encoding="utf-8")
    monkeypatch.setattr(rag, "COURSES", root)
    monkeypatch.setattr(rag, "CACHE", tmp_path / "cache")
    rag.index(root=root, use_embeddings=False)
    r = api.studio_generate(sid, "summary", {"kind": "folder", "folder": "najahni"})
    assert r["refused"] and not r["files"] and not r["items"]
    s2 = api.start_session({"name": "T", "lang": "en"})["session_id"]
    r2 = api.studio_generate(s2, "flashcards", {"kind": "diagnosis"})
    assert r2["refused"] and r2["targeted_at"] is None
    with pytest.raises(NotImplementedError):
        api.studio_generate(s2, "video", {})
