"""Study plan from the student's own files (PDF / TXT / MD).

1. The files are saved to data/courses/uploads/ (the student's own material: allow_derivatives true) and their text
   is extracted page by page (engine/rag.py: PyMuPDF, Arabic checks, OCR if installed).
2. ONE LLM call (engine/llm.py: cached, so the demo replays it offline) turns the pages into a day-by-day plan in
   the student's language. Every day cites the pages it uses; pages that do not exist are removed by code.
   If a diagnosis exists, the plan starts with the diagnosed misconception ("Targeted at").
3. Every text passes the guards in one batch (SymPy claims, congruency, style, language); unsafe items are dropped
   and counted. No LLM output is shown unchecked.
"""
from __future__ import annotations

import hashlib

from engine import guards, llm, rag
from engine.contract import MisconceptionView, PlanDay, Source, StudyPlan
from engine.i18n import lang_of
from engine.studio.flashcards import guards_safetext

ALLOWED = {".pdf", ".txt", ".md"}
MAX_PAGES, PAGE_CHARS = 12, 1100
LANG = {"fr": "French (address the student as \"tu\")", "ar": "Modern Standard Arabic (Arabic script, digits for numbers)",
        "en": "English"}

PLAN_SYS = """You are a study coach. Write a study plan in {lang} for a school student, using ONLY the course pages
below (each starts with its label [file p.N]). {goal}
Rules: {days_rule} Each day: a short title, 1-3 goals, 2-4 concrete tasks (read a page, redo an example, explain a
rule in your own words, solve a question), and the page numbers it uses. Then 3-5 self-check questions taken from the
pages (no answers). Maths as plain text with digits, no LaTeX; every equality must be true; at most {max_words}
words per sentence; no praise, no exclamation marks; do not invent content that is not in the pages.
Return JSON: {{"title": "...", "summary": "...", "days": [{{"day": 1, "title": "...", "goals": ["..."],
"tasks": ["..."], "pages": [{{"file": "...", "page": 1}}]}}], "check_questions": ["..."]}}"""


def save_uploads(files: list[tuple[str, bytes]]) -> list:
    dest = rag.COURSES / "uploads"
    dest.mkdir(parents=True, exist_ok=True)
    meta = dest / "meta.yaml"
    if not meta.exists():
        meta.write_text("# Files uploaded by the user: their own material.\nallow_derivatives: true\n", encoding="utf-8")
    # a file already among the courses (same bytes) is reused, not copied: no duplicate pages in the search index
    known = {hashlib.sha256(f.read_bytes()).hexdigest(): f for f in rag.COURSES.rglob("*")
             if f.is_file() and f.suffix.lower() in ALLOWED}
    out = []
    for name, data in files:
        from pathlib import Path as _P
        n = _P(name or "").name
        if _P(n).suffix.lower() not in ALLOWED:
            raise ValueError(f"{n}: only PDF, TXT and MD files are accepted")
        same = known.get(hashlib.sha256(data).hexdigest())
        if same is not None:
            out.append(same)
            continue
        p = dest / n
        p.write_bytes(data)
        out.append(p)
    return out


def make(files: list[tuple[str, bytes]], details: str, lang: str, kw: dict, suspects: dict[str, str],
         mis_view: dict | None, mis: dict | None) -> dict:
    lang = lang_of(lang)
    if not files:
        raise ValueError("no file")
    paths = save_uploads(files)
    pages: list[tuple[str, int, str]] = []
    unread: list[str] = []
    for p in paths:
        got, bad = rag.extract(p)
        pages += [(p.name, n, t) for n, t, _ in got if t.strip()]
        unread += [f"{p.name} p.{b}" for b in bad]
    if not pages:
        return StudyPlan(title=guards_safetext("", [], lang), summary=None, days=[], check_questions=[], sources=[],
                         targeted_at=None, dropped_by_guards=0,
                         refused="No readable text in these files (scanned pages need OCR).").model_dump()
    pages = pages[:MAX_PAGES]
    text = "\n\n".join(f"[{f} p.{n}] {t.strip()[:PAGE_CHARS]}" for f, n, t in pages)
    goal = (f"The student's diagnosed difficulty is \"{mis['name_en']}\" ({mis.get('description', '')}): put the "
            f"pages about it first." if mis else "")
    days_rule = ("Follow the student's request: " + details.strip()[:300] + ". ") if details.strip() else \
        "Plan 3 to 5 days."
    d = llm.ask_json(PLAN_SYS.format(lang=LANG[lang], goal=goal, days_rule=days_rule,
                                     max_words=kw["max_words_per_sentence"]),
                     f"Course pages:\n{text}", purpose="study_plan", max_tokens=3000) or {}
    valid = {(f, n) for f, n, _ in pages}
    texts: dict[str, str] = {}
    if d.get("title"):
        texts["title"] = str(d["title"])
    if d.get("summary"):
        texts["summary"] = str(d["summary"])
    days_raw = [x for x in (d.get("days") or []) if isinstance(x, dict)][:10]
    for i, day in enumerate(days_raw):
        texts[f"d{i}"] = str(day.get("title", ""))
        for j, g in enumerate(day.get("goals") or []):
            texts[f"d{i}g{j}"] = str(g)
        for j, tk in enumerate(day.get("tasks") or []):
            texts[f"d{i}t{j}"] = str(tk)
    for j, q in enumerate(d.get("check_questions") or []):
        texts[f"q{j}"] = str(q)
    texts = {k: v.strip() for k, v in texts.items() if v.strip()}
    # the judge sees plain numbered ids (x0, x1, …): with word ids it skipped items (no verdict = blocked)
    ids = {f"x{i}": k for i, k in enumerate(texts)}
    judged = guards.check_studio({x: texts[k] for x, k in ids.items()}, suspects, lang,
                                 style_kwargs={**kw, "max_questions": 3}, purpose="study_plan_judge") if texts else {}
    checks = {k: judged[x] for x, k in ids.items()}
    safe = {k: guards_safetext(v, checks[k], lang) for k, v in texts.items()}
    ok = {k: v for k, v in safe.items() if v.shown_allowed}
    dropped = len(safe) - len(ok)
    days = []
    for i, day in enumerate(days_raw):
        if f"d{i}" not in ok:
            continue
        srcs = []
        for s in day.get("pages") or []:
            f, n = (s.get("file"), s.get("page")) if isinstance(s, dict) else (None, s)
            f = f if (f, n) in valid else next((ff for ff, nn in valid if nn == n), None)  # repair a wrong name
            if f and (f, n) in valid and not any(x.file == f and x.page == n for x in srcs):
                srcs.append(Source(file=f, page=int(n)))
        days.append(PlanDay(day=len(days) + 1, title=ok[f"d{i}"],
                            goals=[ok[k] for k in sorted(ok) if k.startswith(f"d{i}g")],
                            tasks=[ok[k] for k in sorted(ok) if k.startswith(f"d{i}t")], sources=srcs))
    return StudyPlan(title=ok.get("title") or guards_safetext("", [], lang), summary=ok.get("summary"), days=days,
                     check_questions=[ok[k] for k in sorted(ok) if k.startswith("q")],
                     sources=[Source(file=f, page=n) for f, n, _ in pages],
                     targeted_at=MisconceptionView(**mis_view) if mis_view else None,
                     dropped_by_guards=dropped, unreadable_pages=unread,
                     plan_id=hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]).model_dump()
