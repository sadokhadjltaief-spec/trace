"""Course-folder retrieval with page citations (CLAUDE.md section 6). 100 % local: no LLM call.

Pipeline: PDF/TXT -> text per page (PyMuPDF; OCR with pytesseract if installed, else the page is logged as
unreadable) -> Arabic checks (presentation forms normalised, reversed text flagged and fixed) -> chunks of about
300-500 tokens with metadata -> BM25 + multilingual embeddings (intfloat/multilingual-e5-small, cached by file
hash) -> reciprocal rank fusion. If the embedding model cannot load, retrieval is BM25 only (reported).

Course Q&A is EXTRACTIVE: it returns the retrieved passages with file + page (+ source link); if nothing is
relevant it says so. No LLM summary (paused: free-tier token budget, 2026-11-21).
Najahni policy (docs/NAJAHNI_NOTE.md): retrieval with citation only; derivatives need allow_derivatives: true
in the folder's meta.yaml.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml

from engine import ROOT
from engine.config import cfg

COURSES = ROOT / "data" / "courses"
CACHE = ROOT / ".cache" / "rag"
TEXT_EXT = {".pdf", ".txt", ".md"}
_AR = re.compile(r"[؀-ۿ]")
_AR_PRES = re.compile(r"[ﭐ-﷿ﹰ-﻿]")  # Arabic presentation forms (common in PDF extraction)
_AR_DIAC = re.compile(r"[ً-ْـ]")         # harakat + tatweel
_WORD = re.compile(r"\w+", re.U)


def _c() -> dict:
    return {"chunk_words": 300, "top_k": 5, "rrf_k": 60, "min_cosine": 0.85,
            "embed_model": "intfloat/multilingual-e5-small", **(cfg().get("rag") or {})}


# ---------------------------------------------------------------- folder metadata
def folder_meta(folder: Path) -> dict:
    """meta.yaml: allow_derivatives (default false for najahni, true for the user's own folders)."""
    p = folder / "meta.yaml"
    meta = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    meta = meta or {}
    meta.setdefault("allow_derivatives", folder.name.lower() != "najahni")
    return meta


def source_urls(folder: Path) -> dict[str, str]:
    """SOURCES.md lines like '- file.pdf: https://...' -> {file: url} (recorded by the human)."""
    p = folder / "SOURCES.md"
    if not p.exists():
        return {}
    out = {}
    for m in re.finditer(r"^\s*[-*]\s*([^:\n]+?\.(?:pdf|txt|md))\s*[:|]\s*(https?://\S+)", p.read_text(encoding="utf-8"),
                         re.M | re.I):
        out[m.group(1).strip()] = m.group(2).strip()
    return out


# ---------------------------------------------------------------- Arabic checks
def fix_arabic(text: str) -> tuple[str, list[str]]:
    """Normalise presentation forms (NFKC) and detect/fix reversed Arabic words. Returns (text, flags)."""
    flags = []
    if _AR_PRES.search(text):
        flags.append("arabic_presentation_forms_normalised")
        text = unicodedata.normalize("NFKC", text)
    words = [w for w in _WORD.findall(text) if _AR.search(w) and len(w) > 2]
    if len(words) >= 5:
        starts = sum(bool(re.match("^[وبفلك]?ال", w)) for w in words)        # al- (with a 1-letter prefix)
        ends_rev = sum(bool(re.search("لا[وبفلك]?$", w)) for w in words)  # the same, reversed
        if ends_rev >= 3 and ends_rev > 2 * max(starts, 1):
            flags.append("arabic_reversed_fixed")
            text = re.sub(r"[؀-ۿ]+", lambda m: m.group(0)[::-1], text)
    return text, flags


def tokens(text: str) -> list[str]:
    t = _AR_DIAC.sub("", unicodedata.normalize("NFKC", text.lower()))
    return [w for w in _WORD.findall(t) if len(w) > 1 or w.isdigit()]


# ---------------------------------------------------------------- extraction + chunking
@dataclass
class Chunk:
    folder: str
    file: str
    page: int
    text: str
    lang: str
    allow_derivatives: bool
    source_url: str | None = None
    flags: list[str] = field(default_factory=list)


def _ocr(page) -> str:
    try:
        import pytesseract  # optional; needs the Tesseract binary with ara+fra+eng
        from PIL import Image
    except ImportError:
        return ""
    pix = page.get_pixmap(dpi=200)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang="ara+fra+eng")


def extract(path: Path) -> tuple[list[tuple[int, str, list[str]]], list[int]]:
    """[(page, text, flags)], unreadable pages."""
    pages, unreadable = [], []
    if path.suffix.lower() in (".txt", ".md"):
        t, fl = fix_arabic(path.read_text(encoding="utf-8", errors="replace"))
        return [(1, t, fl)], []
    import pymupdf
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, 1):
            # expand ligatures ("ﬁ" was extracted as an unknown character: "Dé\x1cnir" instead of "Définir")
            t = page.get_text("text", flags=pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES) or ""
            t = t.replace("\x1c", "fi").replace("\x1d", "fl").replace("ﬁ", "fi").replace("ﬂ", "fl")
            fl = []
            if len(t.strip()) < 50:
                o = _ocr(page)
                if len(o.strip()) >= 50:
                    t, fl = o, ["ocr"]
                else:
                    unreadable.append(i)
                    continue
            t, f2 = fix_arabic(t)
            pages.append((i, t, fl + f2))
    return pages, unreadable


def chunk_page(text: str, max_words: int) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [text.strip()]
    out, cur = [], []
    for p in paras:
        w = p.split()
        if cur and len(cur) + len(w) > max_words:
            out.append(" ".join(cur))
            cur = []
        cur += w
        while len(cur) > max_words * 1.5:
            out.append(" ".join(cur[:max_words]))
            cur = cur[max_words:]
    if cur:
        out.append(" ".join(cur))
    return [o for o in out if len(o) >= 20]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:20]


# ---------------------------------------------------------------- embeddings
_MODEL = None
_MODEL_ERR: str | None = None


def embedder():
    """The multilingual embedding model, or None (BM25-only) if it cannot load."""
    global _MODEL, _MODEL_ERR
    if _MODEL is None and _MODEL_ERR is None:
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer(_c()["embed_model"])
        except Exception as e:  # noqa: BLE001
            _MODEL_ERR = f"{type(e).__name__}: {str(e)[:120]}"
    return _MODEL


def embed(texts: list[str], kind: str) -> np.ndarray | None:
    m = embedder()
    if m is None:
        return None
    prefix = "query: " if kind == "query" else "passage: "  # e5 convention
    return np.asarray(m.encode([prefix + t for t in texts], normalize_embeddings=True, batch_size=32),
                      dtype=np.float32)


# ---------------------------------------------------------------- index
@dataclass
class Index:
    chunks: list[Chunk]
    emb: np.ndarray | None
    report: dict

    def __post_init__(self):
        from rank_bm25 import BM25Okapi
        self._toks = [tokens(c.text) for c in self.chunks]
        self.bm25 = BM25Okapi(self._toks) if self.chunks else None

    def search(self, query: str, k: int | None = None) -> list[dict]:
        c = _c()
        k = k or c["top_k"]
        if not self.chunks:
            return []
        qt = tokens(query)
        bm = np.asarray(self.bm25.get_scores(qt)) if qt else np.zeros(len(self.chunks))
        qset = {w for w in qt if len(w) > 2}  # meaningful query words
        # relevance gate: share of the query words found in the chunk (BM25 scores can be <= 0 in tiny corpora)
        lex = np.asarray([len(qset & set(t)) / len(qset) if qset else 0.0 for t in self._toks])
        cos = None
        if self.emb is not None:
            qv = embed([query], "query")
            cos = self.emb @ qv[0] if qv is not None else None
        rrf = np.zeros(len(self.chunks))
        for scores in [bm] + ([cos] if cos is not None else []):
            order = np.argsort(-scores)
            ranks = np.empty(len(order))
            ranks[order] = np.arange(1, len(order) + 1)
            rrf += 1.0 / (c["rrf_k"] + ranks)
        hits = []
        for i in np.argsort(-rrf)[:k]:
            relevant = bool(lex[i] >= 0.5) or (cos is not None and float(cos[i]) >= c["min_cosine"])
            hits.append({**asdict(self.chunks[i]), "score": round(float(rrf[i]), 5), "bm25": round(float(bm[i]), 3),
                         "cosine": round(float(cos[i]), 4) if cos is not None else None, "relevant": relevant})
        return hits


def build_index(root: Path | None = None, use_embeddings: bool = True) -> Index:
    """Index every PDF/TXT under data/courses/<folder>/ (or `root`). Chunks and embeddings cached by file hash."""
    root = Path(root or COURSES)
    CACHE.mkdir(parents=True, exist_ok=True)
    chunks: list[Chunk] = []
    vecs: list[np.ndarray] = []
    report = {"root": str(root), "files": [], "unreadable_pages": {}, "flags": {}, "embeddings": None}
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in TEXT_EXT and p.is_file()
                   and p.name not in ("SOURCES.md", "README.md"))
    emb_ok = use_embeddings and bool(files) and embedder() is not None
    report["embeddings"] = _c()["embed_model"] if emb_ok else f"off ({_MODEL_ERR or 'disabled'}): BM25 only"
    for f in files:
        folder = f.parent
        meta = folder_meta(folder)
        url = source_urls(folder).get(f.name)
        key = CACHE / f"{_sha(f)}_{_c()['chunk_words']}"
        if key.with_suffix(".json").exists():
            d = json.loads(key.with_suffix(".json").read_text(encoding="utf-8"))
            fchunks = [Chunk(**x) for x in d["chunks"]]
            unread = d["unreadable"]
        else:
            from engine.detector import detect_language
            pages, unread = extract(f)
            fchunks = [Chunk(folder=folder.name, file=str(f.relative_to(root)).replace("\\", "/"), page=pg,
                             text=t, lang=detect_language(t), allow_derivatives=bool(meta["allow_derivatives"]),
                             source_url=url, flags=fl)
                       for pg, txt, fl in pages for t in chunk_page(txt, _c()["chunk_words"])]
            key.with_suffix(".json").write_text(json.dumps({"chunks": [asdict(x) for x in fchunks],
                                                            "unreadable": unread}, ensure_ascii=False),
                                                encoding="utf-8")
        for x in fchunks:  # metadata can change without the file changing
            x.allow_derivatives, x.source_url = bool(meta["allow_derivatives"]), url
        if emb_ok and fchunks:
            npz = key.with_suffix(".npy")
            if npz.exists():
                v = np.load(npz)
            else:
                v = embed([x.text for x in fchunks], "passage")
                np.save(npz, v)
            vecs.append(v)
        chunks += fchunks
        report["files"].append({"file": str(f.relative_to(root)).replace("\\", "/"), "chunks": len(fchunks),
                                "allow_derivatives": bool(meta["allow_derivatives"])})
        if unread:
            report["unreadable_pages"][f.name] = unread
        fl = sorted({g for x in fchunks for g in x.flags})
        if fl:
            report["flags"][f.name] = fl
    emb = np.vstack(vecs) if (emb_ok and vecs) else None
    report["chunks"] = len(chunks)
    return Index(chunks, emb, report)


_INDEX: Index | None = None


def index(refresh: bool = False, root: Path | None = None, use_embeddings: bool = True) -> Index:
    global _INDEX
    if _INDEX is None or refresh or root is not None:
        _INDEX = build_index(root, use_embeddings)
    return _INDEX


def snippet(text: str, query: str, n: int = 320) -> str:
    """The part of the chunk around the first query word (extractive; never rewritten)."""
    qt = [t for t in tokens(query) if len(t) > 2]
    low = text.lower()
    pos = min([low.find(t) for t in qt if low.find(t) >= 0] or [0])
    start = max(0, pos - n // 3)
    s = text[start:start + n].strip()
    return ("…" if start > 0 else "") + s + ("…" if start + n < len(text) else "")
