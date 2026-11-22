"""Interactive textbook: a PDF attached in the tutor chat, or a tutor explanation, turned into lessons ("spreads").

Each spread (left page / right page of the open book):
- title + core concept (2 sentences), a formula / key-principle box, 3-4 vocabulary terms,
- a prediction question (multiple choice) answered BEFORE the visual; the answer key and the "why" stay on the
  server and are revealed under the lift-the-flap only after the student chose,
- a visual: one computed diagram from the media whitelist (drawn by matplotlib, values computed) and, when it fits,
  one simple 3D model from a fixed list (prism, box, cylinder, cone, sphere, pyramid, vectors, wave, curve) - never an
  invented "accurate 3D scientific model".
Checks: every text passes the SymPy math check and the congruency/style judge (one call); every prediction question is
answered blind by a second call and kept only if both agree (same cross-check as the practice quiz).
Completion is computed by the server from real interactions: prediction answered + flap opened + vocabulary viewed +
visual explored. A correct / wrong prediction is also added to the student's learning memory.
"""
from __future__ import annotations

import hashlib
import json
import re
import time

from pydantic import BaseModel, Field, ValidationError

from engine import guards, llm, media, students
from engine.i18n import lang_of

LANG = {"fr": "French", "ar": "Modern Standard Arabic", "en": "English"}
MODELS_3D = ("none", "prism", "box", "cylinder", "cone", "sphere", "pyramid", "vectors", "wave", "curve")
REQUIRED = ("answered", "flap", "vocab", "visual")


class Vocab(BaseModel):
    term: str = Field(max_length=60)
    definition: str = Field(max_length=200)


class Prediction(BaseModel):
    question: str = Field(max_length=300)
    options: list[str] = Field(min_length=3, max_length=4)
    correct: int
    why: str = Field(max_length=600)


class Model3D(BaseModel):
    kind: str = "none"
    label: str = Field("", max_length=80)
    params: dict = {}


class Spread(BaseModel):
    title: str = Field(max_length=90)
    concept: str = Field(max_length=420)
    key_label: str = Field("", max_length=40)
    key: str = Field(max_length=300)
    vocab: list[Vocab] = Field(min_length=2, max_length=4)
    prediction: Prediction
    diagram: dict | None = None
    model3d: Model3D = Model3D()
    pages: list[int] = []


SYS = """You turn a school lesson into an interactive textbook, in {lang}. Split the material into {n} sequential lessons
("spreads"), in the material's order, using ONLY what the material says (its terminology; never invent facts).
For each spread return:
- "title" (max 8 words), "concept": exactly two clear sentences,
- "key_label" ("Formule", "Règle", "Principe"... in {lang}) and "key": the formula, rule or key principle from the
  material, plain text with Unicode (x², √, π, Δ), no LaTeX; every equality must be true,
- "vocab": 3 or 4 essential terms with a one-line definition,
- "prediction": a multiple-choice question that tests intuition BEFORE seeing the visual: "question", 3 or 4
  "options", "correct" (0-based index), "why" (2-3 sentences: why it is right and the underlying idea),
- "diagram": one diagram that shows the lesson, or null. {spec}
- "model3d": a simple 3D model ONLY if the lesson is about a solid, a vector, a wave or a curve, else
  {{"kind": "none"}}. Kinds: prism, box, cylinder, cone, sphere, pyramid (params: width, height, depth or radius),
  vectors (params: "vectors": [[x,y,z], ...] up to 3), wave (params: amplitude, wavelength), curve (params:
  "expression" in x, x_min, x_max). "label": what it shows.
- "pages": the page numbers of the material used (if pages are given).
Return JSON: {{"title": "book title", "spreads": [...]}}"""

BLIND = """Answer each multiple-choice question. Return JSON {"answers": [{"id": "q0", "index": 0}]} with the 0-based index
of the correct option; use -1 if no option is clearly correct."""


def _db():
    c = students._db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS textbooks (id TEXT PRIMARY KEY, student_id TEXT, source TEXT, title TEXT,
        lang TEXT, spreads TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS textbook_progress (textbook_id TEXT, student_key TEXT, spread INTEGER, events TEXT,
        choice INTEGER, correct INTEGER, completed INTEGER, updated REAL, PRIMARY KEY (textbook_id, student_key, spread));
    """)
    return c


def _texts(sp: Spread) -> dict[str, str]:
    t = {"t": sp.title, "c": sp.concept, "k": sp.key, "q": sp.prediction.question, "w": sp.prediction.why}
    for i, v in enumerate(sp.vocab):
        t[f"v{i}"] = f"{v.term}: {v.definition}"
    for i, o in enumerate(sp.prediction.options):
        t[f"o{i}"] = o
    return t


def make(lang: str = "fr", doc_id: str | None = None, text: str | None = None, student: dict | None = None) -> dict:
    """Build (or return the cached) textbook for a document or an explanation."""
    from engine import documents
    lang = lang_of(lang)
    if doc_id:
        name, pages = documents.full_text(doc_id)
        material = "\n\n".join(f"[page {p['page']}] {p['text']}" for p in pages)
        source = f"doc:{doc_id}"
        n = "3 to 6" if len(pages) > 2 else "2 to 3"
    elif text and text.strip():
        name, material, source, n = "", text.strip()[:6000], "text:" + hashlib.sha1(text.encode()).hexdigest()[:12], "1 to 3"
    else:
        raise ValueError("no material")
    tb_id = "tb-" + hashlib.sha1(f"{source}|{lang}".encode()).hexdigest()[:14]
    with _db() as c:
        row = c.execute("SELECT id FROM textbooks WHERE id=?", (tb_id,)).fetchone()
    if row:
        return get(tb_id, student)
    try:
        d = llm.ask_json(SYS.format(lang=LANG[lang], n=n, spec=media.SPEC_DOC.replace("\n", " ")),
                         f"Material{(' (' + name + ')') if name else ''}:\n{material}", purpose="textbook",
                         max_tokens=4000) or {}
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"textbook unavailable: {str(e)[:120]}") from e
    spreads: list[Spread] = []
    for raw in (d.get("spreads") or [])[:6]:
        try:
            sp = Spread.model_validate(raw)
        except ValidationError:
            continue
        if not 0 <= sp.prediction.correct < len(sp.prediction.options):
            continue
        if sp.model3d.kind not in MODELS_3D:
            sp.model3d = Model3D()
        elif sp.model3d.kind == "curve":
            sp.model3d = _curve_points(sp.model3d)
        spreads.append(sp)
    if not spreads:
        raise ValueError("textbook unavailable: no valid lesson")
    # 1) math + congruency/style judge on every text (one call)
    texts = {f"s{i}{k}": v for i, sp in enumerate(spreads) for k, v in _texts(sp).items()}
    checks = guards.check_studio(texts, {}, lang, style_kwargs={"max_words_per_sentence": 45, "max_questions": 3,
                                                               "neutral": False, "lang": lang}, purpose="textbook_judge")
    bad = {k[:2] for k, cs in checks.items() if any(c.status == "fail" and c.name in ("math", "congruency") for c in cs)}
    # 2) blind answers: keep a prediction only if an independent call finds the same option
    qs = "\n\n".join(f"[q{i}] {sp.prediction.question}\n" + "\n".join(f"{j}. {o}" for j, o in
                     enumerate(sp.prediction.options)) for i, sp in enumerate(spreads))
    try:
        blind = {a.get("id"): a.get("index") for a in (llm.ask_json(BLIND, qs, purpose="textbook_blind",
                                                                    max_tokens=1500) or {}).get("answers", [])}
    except Exception:  # noqa: BLE001
        blind = {}
    kept = []
    for i, sp in enumerate(spreads):
        if f"s{i}" in bad or blind.get(f"q{i}") != sp.prediction.correct:
            continue
        diag = media._spec_from(sp.diagram) if sp.diagram else None
        img = None
        if diag:
            name_png = media._key("tb", diag.model_dump(), lang) + ".png"
            path = media.OUT / name_png
            if not path.exists():
                media.render(diag, path, lang)
            img = {"url": f"/engine/media/{name_png}", "title": diag.title, "caption": diag.caption, "kind": diag.kind}
        kept.append({**sp.model_dump(exclude={"diagram"}), "image": img})
    if not kept:
        raise ValueError("textbook unavailable: no lesson passed the checks")
    with _db() as c:
        c.execute("INSERT OR REPLACE INTO textbooks VALUES (?,?,?,?,?,?,?)",
                  (tb_id, (student or {}).get("student_id"), source, str(d.get("title") or name or kept[0]["title"])[:90],
                   lang, json.dumps(kept, ensure_ascii=False), time.time()))
    return get(tb_id, student)


def _curve_points(m: Model3D) -> Model3D:
    """y = f(x) sampled with SymPy here (the browser only draws the points; nothing is evaluated there)."""
    import numpy as np
    import sympy as sp
    x = sp.Symbol("x")
    try:
        expr = sp.sympify(str(m.params.get("expression", "")).replace("^", "**"), locals={"x": x})
        if expr.free_symbols - {x}:
            raise ValueError("other variables")
        lo, hi = float(m.params.get("x_min", -2)), float(m.params.get("x_max", 2))
        if not -100 < lo < hi < 100:
            lo, hi = -2.0, 2.0
        xs = np.linspace(lo, hi, 120)
        ys = np.asarray(sp.lambdify(x, expr, "numpy")(xs), dtype=float) * np.ones_like(xs)
        pts = [[round(float(a), 4), round(float(b), 4)] for a, b in zip(xs, ys) if np.isfinite(b)]
        return Model3D(kind="curve", label=m.label or f"y = {expr}", params={"points": pts, "expression": str(expr)})
    except Exception:  # noqa: BLE001
        return Model3D()


def _key_of(student: dict | None, guest: str | None) -> str:
    return (student or {}).get("student_id") or f"guest:{guest or '-'}"


def get(tb_id: str, student: dict | None = None, guest: str | None = None) -> dict:
    """The textbook WITHOUT answer keys (correct index and why stay here until the student answers)."""
    with _db() as c:
        row = c.execute("SELECT id, source, title, lang, spreads FROM textbooks WHERE id=?", (tb_id,)).fetchone()
        if not row:
            raise KeyError(tb_id)
        prog = {r[0]: r for r in c.execute("SELECT spread, events, choice, correct, completed FROM textbook_progress "
                                           "WHERE textbook_id=? AND student_key=?", (tb_id, _key_of(student, guest)))}
    spreads = json.loads(row[4])
    out = []
    for i, sp in enumerate(spreads):
        p = prog.get(i)
        answered = p is not None and p[2] is not None
        pred = {"question": sp["prediction"]["question"], "options": sp["prediction"]["options"]}
        if answered:  # already answered: the flap content can be shown again
            pred |= {"choice": p[2], "correct_index": sp["prediction"]["correct"], "why": sp["prediction"]["why"],
                     "was_correct": bool(p[3])}
        out.append({**{k: sp[k] for k in ("title", "concept", "key_label", "key", "vocab", "model3d", "pages", "image")},
                    "prediction": pred, "events": json.loads(p[1]) if p else [], "completed": bool(p and p[4])})
    return {"textbook_id": row[0], "source": row[1], "title": row[2], "lang": row[3], "spreads": out,
            "completed": sum(1 for s in out if s["completed"]), "required": list(REQUIRED)}


def _progress(tb_id: str, i: int, key: str, event: str | None = None, choice: int | None = None,
              correct: bool | None = None) -> dict:
    with _db() as c:
        row = c.execute("SELECT events, choice, correct FROM textbook_progress WHERE textbook_id=? AND student_key=? "
                        "AND spread=?", (tb_id, key, i)).fetchone()
        events = set(json.loads(row[0])) if row else set()
        ch, co = (row[1], row[2]) if row else (None, None)
        if event:
            events.add(event)
        if choice is not None and ch is None:
            ch, co = choice, int(bool(correct))
            events.add("answered")
        done = all(e in events for e in REQUIRED)
        c.execute("INSERT OR REPLACE INTO textbook_progress VALUES (?,?,?,?,?,?,?,?)",
                  (tb_id, key, i, json.dumps(sorted(events)), ch, co, int(done), time.time()))
    return {"events": sorted(events), "completed": done}


def _spread(tb_id: str, i: int) -> dict:
    with _db() as c:
        row = c.execute("SELECT spreads FROM textbooks WHERE id=?", (tb_id,)).fetchone()
    if not row:
        raise KeyError(tb_id)
    spreads = json.loads(row[0])
    if not 0 <= i < len(spreads):
        raise KeyError(f"spread {i}")
    return spreads[i]


def answer(tb_id: str, i: int, choice: int, student: dict | None = None, guest: str | None = None) -> dict:
    """Grade the prediction (answer key, deterministic), reveal the flap, update progress and learning memory."""
    sp = _spread(tb_id, i)
    if not 0 <= choice < len(sp["prediction"]["options"]):
        raise ValueError("bad choice")
    key = _key_of(student, guest)
    prev = _progress(tb_id, i, key)
    ok = choice == sp["prediction"]["correct"]
    st = _progress(tb_id, i, key, choice=choice, correct=ok)
    if student and "answered" not in prev["events"]:
        students.observe(student["student_id"], [{"concept": sp["title"], "subject": "",
                                                  "status": "understood" if ok else "struggling",
                                                  "note": "prédiction du manuel " + ("juste" if ok else "fausse")}])
    return {"correct": ok, "correct_index": sp["prediction"]["correct"], "why": sp["prediction"]["why"], **st}


def event(tb_id: str, i: int, name: str, student: dict | None = None, guest: str | None = None) -> dict:
    if name not in ("flap", "vocab", "visual"):
        raise ValueError("unknown event")
    _spread(tb_id, i)
    key = _key_of(student, guest)
    if name == "flap":
        with _db() as c:
            r = c.execute("SELECT choice FROM textbook_progress WHERE textbook_id=? AND student_key=? AND spread=?",
                          (tb_id, key, i)).fetchone()
        if not r or r[0] is None:
            raise ValueError("answer the prediction first")  # the flap opens only after a choice
    return _progress(tb_id, i, key, event=name)
