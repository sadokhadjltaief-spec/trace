"""Study plan from the student's own files (PDF / TXT / MD), built from the CONTENT, not the page numbers.

1. The files are saved to data/courses/uploads/ (the student's own material; a file identical to an existing course
   file is reused) and their text is extracted page by page (engine/rag.py: ligatures expanded, Arabic checks).
2. The pages are cleaned by code: lines repeated on most pages (headers, footers, "12 / 51") are removed, duplicate
   pages (an outline repeated on every slide) are merged, and the WHOLE document is kept within a text budget.
3. ONE LLM call (cached: the demo replays it offline) first extracts the real chapters and concepts, then builds a
   day-by-day revision programme in the student's language: "Study: <chapter>", 3-5 concrete tasks (exercises,
   formulas to learn, flashcards, self-test, explain in your own words), a duration and the pages. Pages that do not
   exist are removed by code. If a diagnosis exists, the diagnosed difficulty comes first ("Targeted at").
4. Every text passes the guards (SymPy claims, congruency, style, language) in small batches; unsafe items are
   dropped and counted.
5. Without the LLM (offline and not cached): a plan built by code from the detected sections (headings), never
   "read page N".
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter

from engine import guards, llm, rag
from engine.contract import MisconceptionView, PageText, PlanChapter, PlanDay, Source, StudyPlan
from engine.i18n import lang_of
from engine.studio.flashcards import guards_safetext

ALLOWED = {".pdf", ".txt", ".md"}
TEXT_BUDGET = 8000          # characters of course text sent to the LLM (~2.5k tokens; Groq free tier: 8k tokens/min)
JUDGE_BATCH = 12
LANG = {"fr": "French (address the student as \"tu\")", "ar": "Modern Standard Arabic (Arabic script, digits for numbers)",
        "en": "English"}

PLAN_SYS = """You are an expert study coach (like a good revision app). Build a revision programme in {lang} for a
student, from the course pages below (each starts with its label [file p.N]). {goal}
Step 1, analyse the CONTENT: list the real chapters / sections of the course (use the course's own titles), the key
concepts of each (definitions, laws, methods), and the pages where they are.
Step 2, plan: {days_rule} One day = one focus; EVERY chapter found in step 1 must be studied on at least one day
before the final review day. Each day has:
- "title": "Study: <chapter or section title>" written in {lang} (e.g. "Étudier : Le premier principe"),
- "duration_min": 30 to 60,
- "goals": 1-3 precise learning goals naming the concepts,
- "tasks": 3-5 CONCRETE tasks with quantities, mixing: learn a definition or formula by name, redo or solve N
  exercises/examples on a named concept, make N flashcards on named terms, explain a named idea in 3 sentences,
  self-test with a question; the last day is a global review,
- "pages": the pages used.
Then "formulas": up to 6 key formulas or rules copied from the pages (plain text), and "check_questions": 4-6
self-check questions on the concepts (no answers).
Rules: use ONLY the content of the pages, never "read page N" as a task; maths as plain text, no LaTeX; every
numeric equality must be true; at most {max_words} words per sentence; no praise, no exclamation marks.
Return JSON: {{"title": "...", "summary": "...", "chapters": [{{"title": "...", "concepts": ["..."], "pages": [1, 2]}}],
"days": [{{"day": 1, "title": "...", "duration_min": 45, "goals": ["..."], "tasks": ["..."],
"pages": [{{"file": "...", "page": 1}}]}}], "formulas": ["..."], "check_questions": ["..."]}}"""

_PAGE_NO = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")


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


def clean_pages(pages: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """Remove repeated header/footer lines and page counters; merge duplicate pages (e.g. a repeated outline)."""
    lines_per_page = [[ln.strip() for ln in t.splitlines() if ln.strip()] for _, _, t in pages]
    freq = Counter(ln for lines in lines_per_page for ln in set(lines))
    n = len(pages)
    repeated = {ln for ln, c in freq.items() if n >= 4 and c >= max(3, 0.4 * n)}
    out, seen = [], []
    for (f, p, _), lines in zip(pages, lines_per_page):
        keep = [ln for ln in lines if ln not in repeated and not _PAGE_NO.match(ln)]
        if not keep:
            continue
        words = set(re.findall(r"\w+", " ".join(keep).lower()))
        if len(words) >= 8 and any(len(words & s) / max(len(words | s), 1) >= 0.9 for s in seen):
            continue  # near-duplicate of an earlier page (e.g. the outline repeated on every section slide)
        seen.append(words)
        out.append((f, p, "\n".join(keep)))
    return out or pages


def sections(pages: list[tuple[str, int, str]]) -> list[dict]:
    """Group consecutive pages that start with the same heading (slides of one section)."""
    out: list[dict] = []
    for f, p, t in pages:
        head = t.splitlines()[0].strip()[:80] if t.strip() else f"{f} p.{p}"
        if out and out[-1]["title"] == head and out[-1]["file"] == f:
            out[-1]["pages"].append(p)
            out[-1]["text"] += "\n" + t
        else:
            out.append({"title": head, "file": f, "pages": [p], "text": t})
    return out


def budget_text(pages: list[tuple[str, int, str]]) -> str:
    per = max(160, TEXT_BUDGET // max(len(pages), 1))
    return "\n\n".join(f"[{f} p.{n}] {t[:per]}" for f, n, t in pages)[:TEXT_BUDGET + 2000]


def fallback_plan(pages: list[tuple[str, int, str]], lang: str, kw: dict, mis_view: dict | None,
                  unread: list[str]) -> dict:
    """No LLM: one day per detected section (merged to at most 6 days), with content-based tasks (i18n)."""
    from engine import safetext
    from engine.i18n import t as tr

    def st(x: str):
        return safetext.static(x, lang=lang, style_kwargs={**kw, "max_words_per_sentence": 40, "max_questions": 3})
    secs = sections(pages)
    while len(secs) > 6:  # merge the two smallest neighbours
        i = min(range(len(secs) - 1), key=lambda k: len(secs[k]["pages"]) + len(secs[k + 1]["pages"]))
        a, b = secs[i], secs.pop(i + 1)
        a["pages"] += b["pages"]
        a["title"] = a["title"] if len(a["pages"]) - len(b["pages"]) >= len(b["pages"]) else b["title"]
    days = []
    for i, s in enumerate(secs, 1):
        pg = f"{s['pages'][0]}" if len(s["pages"]) == 1 else f"{s['pages'][0]}-{s['pages'][-1]}"
        days.append(PlanDay(day=i, title=st(tr("plan_study", lang, topic=s["title"])), goals=[],
                            tasks=[st(tr("plan_task_notes", lang, topic=s["title"], pages=pg)),
                                   st(tr("plan_task_examples", lang)), st(tr("plan_task_cards", lang)),
                                   st(tr("plan_task_explain", lang))],
                            sources=[Source(file=s["file"], page=p) for p in s["pages"]], duration_min=40))
    return StudyPlan(title=st(tr("plan_fallback_title", lang)), summary=st(tr("plan_fallback_summary", lang)),
                     days=days, check_questions=[],
                     chapters=[PlanChapter(title=st(s["title"]), concepts=[], pages=s["pages"]) for s in secs],
                     sources=[Source(file=f, page=n) for f, n, _ in pages],
                     targeted_at=MisconceptionView(**mis_view) if mis_view else None, dropped_by_guards=0,
                     unreadable_pages=unread, plan_id="fallback",
                     page_texts=[PageText(file=f, page=n, text=t[:6000]) for f, n, t in pages]).model_dump()


def _guard(texts: dict[str, str], suspects: dict, lang: str, kw: dict) -> dict:
    """check_studio in small batches with numbered ids (word ids made the judge skip items)."""
    keys = list(texts)
    out = {}
    for s in range(0, len(keys), JUDGE_BATCH):
        part = keys[s:s + JUDGE_BATCH]
        ids = {f"x{i}": k for i, k in enumerate(part)}
        judged = guards.check_studio({x: texts[k] for x, k in ids.items()}, suspects, lang,
                                     style_kwargs={**kw, "max_questions": 3, "max_words_per_sentence": 40},
                                     purpose="study_plan_judge")
        out.update({k: judged[x] for x, k in ids.items()})
    return out


def make(files: list[tuple[str, bytes]], details: str, lang: str, kw: dict, suspects: dict[str, str],
         mis_view: dict | None, mis: dict | None) -> dict:
    lang = lang_of(lang)
    if not files:
        raise ValueError("no file")
    paths = save_uploads(files)
    raw: list[tuple[str, int, str]] = []
    unread: list[str] = []
    for p in paths:
        got, bad = rag.extract(p)
        raw += [(p.name, n, t) for n, t, _ in got if t.strip()]
        unread += [f"{p.name} p.{b}" for b in bad]
    if not raw:
        return StudyPlan(title=guards_safetext("", [], lang), summary=None, days=[], check_questions=[], sources=[],
                         targeted_at=None, dropped_by_guards=0,
                         refused="No readable text in these files (scanned pages need OCR).").model_dump()
    pages = clean_pages(raw)
    text = budget_text(pages)
    goal = (f"The student's diagnosed difficulty is \"{mis['name_en']}\" ({mis.get('description', '')}): plan it "
            f"first." if mis else "")
    days_rule = ("Follow the student's request: " + details.strip()[:300] + ".") if details.strip() else \
        "Choose 3 to 6 days depending on the amount of content."
    try:
        d = llm.ask_json(PLAN_SYS.format(lang=LANG[lang], goal=goal, days_rule=days_rule,
                                         max_words=max(kw["max_words_per_sentence"], 25)),
                         f"Course pages:\n{text}", purpose="study_plan_v2", max_tokens=4000) or {}
        if not d.get("days"):
            raise ValueError("empty plan")
    except Exception:  # noqa: BLE001  (offline / not cached / API error): plan built by code from the sections
        return fallback_plan(pages, lang, kw, mis_view, unread)
    valid = {(f, n) for f, n, _ in raw}
    texts: dict[str, str] = {}
    for k in ("title", "summary"):
        if d.get(k):
            texts[k] = str(d[k])
    chapters_raw = [c for c in (d.get("chapters") or []) if isinstance(c, dict)][:10]
    for i, c in enumerate(chapters_raw):
        texts[f"c{i}"] = str(c.get("title", ""))
        for j, cc in enumerate((c.get("concepts") or [])[:6]):
            texts[f"c{i}k{j:02d}"] = str(cc)
    days_raw = [x for x in (d.get("days") or []) if isinstance(x, dict)][:10]
    for i, day in enumerate(days_raw):
        texts[f"d{i}"] = str(day.get("title", ""))
        for j, g in enumerate((day.get("goals") or [])[:3]):
            texts[f"d{i}g{j}"] = str(g)
        for j, tk in enumerate((day.get("tasks") or [])[:5]):
            texts[f"d{i}t{j}"] = str(tk)
    for j, fm in enumerate((d.get("formulas") or [])[:6]):
        texts[f"f{j}"] = str(fm)
    for j, q in enumerate((d.get("check_questions") or [])[:6]):
        texts[f"q{j}"] = str(q)
    texts = {k: v.strip() for k, v in texts.items() if v.strip()}
    checks = _guard(texts, suspects, lang, kw)
    safe = {k: guards_safetext(v, checks[k], lang) for k, v in texts.items()}
    ok = {k: v for k, v in safe.items() if v.shown_allowed}
    dropped = len(safe) - len(ok)

    def pick(prefix: str):
        return [ok[k] for k in sorted(ok) if re.fullmatch(prefix + r"\d+", k)]
    days = []
    for i, day in enumerate(days_raw):
        if f"d{i}" not in ok:
            continue
        srcs = []
        for s in day.get("pages") or []:
            f, n = (s.get("file"), s.get("page")) if isinstance(s, dict) else (None, s)
            try:
                n = int(n)
            except (TypeError, ValueError):
                continue
            f = f if (f, n) in valid else next((ff for ff, nn in valid if nn == n), None)  # repair a wrong name
            if f and (f, n) in valid and not any(x.file == f and x.page == n for x in srcs):
                srcs.append(Source(file=f, page=n))
        dur = day.get("duration_min")
        days.append(PlanDay(day=len(days) + 1, title=ok[f"d{i}"], goals=pick(f"d{i}g"), tasks=pick(f"d{i}t"),
                            sources=srcs, duration_min=int(dur) if isinstance(dur, (int, float)) else None))
    chapters = []
    for i, c in enumerate(chapters_raw):
        if f"c{i}" in ok:
            pg = [int(p) for p in (c.get("pages") or []) if isinstance(p, (int, float)) and
                  any(nn == int(p) for _, nn in valid)]
            chapters.append(PlanChapter(title=ok[f"c{i}"], concepts=pick(f"c{i}k"), pages=pg))
    return StudyPlan(title=ok.get("title") or guards_safetext("", [], lang), summary=ok.get("summary"), days=days,
                     chapters=chapters, formulas=pick("f"), check_questions=pick("q"),
                     sources=[Source(file=f, page=n) for f, n, _ in raw],
                     targeted_at=MisconceptionView(**mis_view) if mis_view else None,
                     dropped_by_guards=dropped, unreadable_pages=unread,
                     page_texts=[PageText(file=f, page=n, text=tx[:6000]) for f, n, tx in pages],
                     plan_id=hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]).model_dump()
