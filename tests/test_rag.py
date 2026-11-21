"""Step 11: local retrieval with page citations (no LLM)."""
import unicodedata

import pymupdf
import pytest

from engine import api, rag
from engine.contract import CourseAnswer


def _make_courses(root):
    own = root / "mes_notes"
    own.mkdir(parents=True)
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Chapitre 1 : les fractions.\nPour additionner deux fractions, on les met d'abord\n"
                             "au meme denominateur, puis on additionne les numerateurs.\n"
                             "On n'additionne jamais les denominateurs entre eux.", fontsize=11)
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Chapitre 2 : les nombres relatifs.\nSoustraire un nombre negatif revient a ajouter\n"
                             "son oppose : (-8) - (-5) = -8 + 5.", fontsize=11)
    doc.new_page()  # empty page -> unreadable (no OCR installed)
    doc.save(own / "cours_maths.pdf")
    nj = root / "najahni"
    nj.mkdir()
    (nj / "meta.yaml").write_text("allow_derivatives: false\n", encoding="utf-8")
    (nj / "SOURCES.md").write_text("- lecon.txt: https://example.org/lecon\n", encoding="utf-8")
    (nj / "lecon.txt").write_text("الكسور المتكافئة: نضرب البسط والمقام في العدد نفسه، ولا نضيف العدد نفسه إليهما. "
                                  "مثال: 3/5 = 12/20 لأننا ضربنا في 4.", encoding="utf-8")
    return root


@pytest.fixture
def ix(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "CACHE", tmp_path / "cache")
    root = _make_courses(tmp_path / "courses")
    monkeypatch.setattr(rag, "COURSES", root)
    return rag.index(root=root, use_embeddings=False)


def test_index_report(ix):
    r = ix.report
    assert r["chunks"] >= 3 and "BM25 only" in r["embeddings"]
    assert r["unreadable_pages"] == {"cours_maths.pdf": [3]}
    files = {f["file"]: f for f in r["files"]}
    assert files["najahni/lecon.txt"]["allow_derivatives"] is False
    assert files["mes_notes/cours_maths.pdf"]["allow_derivatives"] is True


def test_search_cites_file_page_and_source(ix):
    hits = [h for h in ix.search("additionner deux fractions denominateur") if h["relevant"]]
    assert hits[0]["file"] == "mes_notes/cours_maths.pdf" and hits[0]["page"] == 1
    hits = [h for h in ix.search("soustraire un nombre negatif") if h["relevant"]]
    assert hits[0]["page"] == 2
    ar = [h for h in ix.search("نضرب البسط والمقام") if h["relevant"]]
    assert ar[0]["file"] == "najahni/lecon.txt" and ar[0]["source_url"] == "https://example.org/lecon"
    assert ar[0]["lang"] == "ar" and ar[0]["allow_derivatives"] is False


def test_nothing_relevant_says_so(ix):
    r = api.course_search("photosynthese chlorophylle")
    CourseAnswer.model_validate(r)
    assert r["found"] is False and not r["hits"] and "does not answer from memory" in r["note"]
    r = api.course_search("additionner deux fractions")
    assert r["found"] and r["hits"][0]["page"] == 1 and "additionner" in r["hits"][0]["snippet"]
    with pytest.raises(ValueError):
        api.course_search("  ")


def test_arabic_checks():
    pres = "ﻟﻠﺎ"  # presentation forms
    t, fl = rag.fix_arabic(pres + " كلمة")
    assert "arabic_presentation_forms_normalised" in fl and t == unicodedata.normalize("NFKC", pres + " كلمة")
    normal = "الكسر والبسط والمقام والعدد والضرب والجمع"
    rev = " ".join(w[::-1] for w in normal.split())
    fixed, fl = rag.fix_arabic(rev)
    assert "arabic_reversed_fixed" in fl and fixed == normal
    assert rag.fix_arabic(normal)[1] == []


def test_lesson_refs_in_report(ix, monkeypatch):
    mv = {"id": "M4", "name_en": "Makes equivalent fractions by adding", "name_fr": "", "name_ar": ""}
    monkeypatch.setattr(api, "_mis", lambda h: {"description": "نضرب البسط والمقام في العدد نفسه"})
    refs = api._lesson_refs(mv)
    assert refs and refs[0].file == "najahni/lecon.txt" and refs[0].source_url
    assert api._lesson_refs({"id": "M0"}) == []


def test_embeddings_if_model_available(tmp_path, monkeypatch):
    if rag.embedder() is None:
        pytest.skip("embedding model not available offline")
    monkeypatch.setattr(rag, "CACHE", tmp_path / "cache")
    root = _make_courses(tmp_path / "courses")
    ix = rag.index(root=root, use_embeddings=True)
    assert ix.emb is not None and ix.emb.shape[0] == len(ix.chunks)
    hits = [h for h in ix.search("comment additionner deux fractions ?") if h["relevant"]]
    assert hits[0]["page"] == 1 and hits[0]["cosine"] is not None
