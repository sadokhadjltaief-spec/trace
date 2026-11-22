"""PDFs attached in the AI tutor chat (student's own course documents).

Upload: the file type is checked by extension AND by its first bytes (%PDF), size <= 25 MB, at most 300 pages. The text
is extracted page by page with PyMuPDF (page numbers kept). Pages with no text layer are reported: OCR runs only if
pytesseract + Tesseract are installed (they are not by default), otherwise the student is told plainly that those pages
need OCR - the tutor is never told it has read pages it could not read.
Retrieval: BM25 over ~250-word chunks of the document (with their page), so the tutor answers from the right pages and
cites them. Files are kept in .cache/tutor_docs/ (gitignored); metadata + page texts in the SQLite database.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from engine import ROOT, rag, students

DIR = ROOT / ".cache" / "tutor_docs"
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 300


class DocError(Exception):
    def __init__(self, key: str, detail: str = ""):
        super().__init__(detail or key)
        self.key = key


def _db():
    c = students._db()
    c.execute("""CREATE TABLE IF NOT EXISTS tutor_docs (id TEXT PRIMARY KEY, student_id TEXT, filename TEXT, size INTEGER,
                 n_pages INTEGER, pages TEXT, unreadable TEXT, created REAL)""")
    return c


def save(filename: str, data: bytes, student_id: str | None = None) -> dict:
    name = Path(filename or "document.pdf").name[:120]
    if not name.lower().endswith(".pdf"):
        raise DocError("doc_not_pdf")
    if not data or not data.startswith(b"%PDF"):
        raise DocError("doc_not_pdf", "missing %PDF header")
    if len(data) > MAX_BYTES:
        raise DocError("doc_too_big")
    doc_id = "doc-" + hashlib.sha256(data + (student_id or "").encode()).hexdigest()[:14]
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"{doc_id}.pdf"
    path.write_bytes(data)
    try:
        import pymupdf
        with pymupdf.open(path) as d:
            n = d.page_count
        if n > MAX_PAGES:
            raise DocError("doc_too_many_pages")
        pages, unreadable = rag.extract(path)
    except DocError:
        raise
    except Exception as e:  # noqa: BLE001  damaged / encrypted file
        raise DocError("doc_unreadable", type(e).__name__) from e
    texts = [{"page": p, "text": t} for p, t, _ in pages if t.strip()]
    with _db() as c:
        c.execute("INSERT OR REPLACE INTO tutor_docs VALUES (?,?,?,?,?,?,?,?)",
                  (doc_id, student_id, name, len(data), n, json.dumps(texts, ensure_ascii=False), json.dumps(unreadable),
                   time.time()))
    return info(doc_id)


def _row(doc_id: str):
    with _db() as c:
        return c.execute("SELECT id, student_id, filename, size, n_pages, pages, unreadable FROM tutor_docs WHERE id=?",
                         (doc_id,)).fetchone()


def info(doc_id: str) -> dict:
    r = _row(doc_id)
    if not r:
        raise KeyError(doc_id)
    pages, unreadable = json.loads(r[5]), json.loads(r[6])
    return {"doc_id": r[0], "filename": r[2], "size": r[3], "pages": r[4], "readable_pages": len(pages),
            "unreadable_pages": unreadable, "needs_ocr": not pages,
            "partly_unreadable": bool(unreadable) and bool(pages)}


def pages(doc_id: str) -> tuple[str, list[dict], list[int]]:
    r = _row(doc_id)
    if not r:
        raise KeyError(doc_id)
    return r[2], json.loads(r[5]), json.loads(r[6])


_OVERVIEW = re.compile(r"(?i)(r[ée]sum|de quoi parle|summar|overview|what is (this|the) (document|pdf) about|"
                       r"tout le (document|cours)|ملخص|عن ماذا)")


def passages(doc_id: str, query: str, k: int = 4) -> tuple[str, list[dict]]:
    """Context block for the tutor + the pages used. Whole-document questions get the first pages."""
    name, pg, unreadable = pages(doc_id)
    if not pg:
        return (f"The student attached \"{name}\" but NO text could be extracted (scanned pages: OCR needed). Say so "
                f"plainly and do not answer as if you had read it.", [])
    chunks = []
    for p in pg:
        words = p["text"].split()
        for s in range(0, len(words), 230):
            chunks.append({"page": p["page"], "text": " ".join(words[s:s + 260])})
    if _OVERVIEW.search(query or ""):
        picked = chunks[:k]
    else:
        from rank_bm25 import BM25Okapi
        toks = [rag.tokens(c["text"]) for c in chunks]
        bm = BM25Okapi(toks)
        scores = bm.get_scores(rag.tokens(query or ""))
        order = sorted(range(len(chunks)), key=lambda i: -scores[i])
        picked = [chunks[i] for i in order[:k] if scores[i] > 0] or chunks[:2]
    note = f" Pages {unreadable} could not be read (OCR needed): say so if the question is about them." if unreadable else ""
    body = "\n".join(f"[{name} p.{c['page']}] {c['text'][:1400]}" for c in picked)
    return (f"The student attached the document \"{name}\" ({len(pg)} readable pages). Answer FIRST from these passages, "
            f"with its terminology, and cite pages as ({name} p.N). Say clearly when you add general knowledge.{note}\n"
            + body), [{"file": name, "page": c["page"], "text": c["text"]} for c in picked]


def full_text(doc_id: str, budget: int = 8000) -> tuple[str, list[dict]]:
    """Text of the whole document within a character budget, page by page (for the textbook)."""
    name, pg, _ = pages(doc_id)
    if not pg:
        raise DocError("doc_needs_ocr")
    per = max(400, budget // max(len(pg), 1))
    return name, [{"page": p["page"], "text": p["text"][:per]} for p in pg][:60]
