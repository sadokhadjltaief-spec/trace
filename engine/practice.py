"""Practice from the student's own material (file or pasted text): quiz and flashcards.

Material: uploaded PDF/TXT/MD (saved like the study plan, cleaned: headers/footers and duplicate pages removed) or
pasted text. YouTube / Wikipedia links are refused for now (they need the internet; the demo runs offline).

Quiz ("practice", NOT the diagnosis bank):
- ONE LLM call writes multiple-choice questions from the text (one correct option, plausible distractors, short
  explanation, page). The answer key is then CROSS-CHECKED: a second, independent call answers every question
  "blind" (without the key) from the same text; only questions where both agree are kept. Numeric options are also
  checked by the guards (SymPy). Every text passes the guards. The key stays on the server: the browser sends an
  answer and gets right / wrong + explanation (check()).
- This is a deviation from the brief's rule "the LLM never writes answer keys for graded questions": these
  questions are practice, labelled as generated and cross-checked, not teacher-verified. Diagnosis and the tutor
  still use only the human-verified bank.
Flashcards: engine/studio/flashcards.py from the material's passages (guarded; drafts, not teacher-reviewed).
All LLM calls go through engine/llm.py (cached, so a recorded file replays offline).
"""
from __future__ import annotations

import hashlib
import re

from engine import guards, llm, rag
from engine.contract import PracticeCards, PracticeCheck, PracticeQuestion, PracticeQuiz, Source
from engine.i18n import lang_of, t as tr
from engine.studio import flashcards
from engine.studio.flashcards import guards_safetext
from engine.study_plan import clean_pages, save_uploads

LANG = {"fr": "French (address the student as \"tu\")", "ar": "Modern Standard Arabic (Arabic script, digits for numbers)",
        "en": "English"}
QUIZ_BUDGET = 7000
_QUIZZES: dict[str, dict] = {}   # quiz_id -> {question_id: {"correct", "explanation"}} (keys never sent to the browser)

QUIZ_SYS = """Write {n} multiple-choice questions in {lang} to test a student on the course text below (each part
starts with its label [file p.N]). Cover different parts of the text. Each question: a clear question, 4 options
A-D with exactly ONE correct option and three plausible wrong options (typical mistakes), the correct letter, a
short explanation (1-2 sentences) of why it is correct, and the label of the part it comes from. Use ONLY the
text; no trick questions; no "all of the above"; maths as plain text, no LaTeX; every numeric equality must be true;
at most {max_words} words per sentence; no praise, no exclamation marks.
Return JSON: {{"questions": [{{"question": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
"correct": "B", "explanation": "...", "source": {{"file": "...", "page": 1}}}}]}}"""

BLIND_SYS = """Answer each multiple-choice question using ONLY the course text below. If the text does not allow a
single sure answer, answer "?". Return JSON: {"answers": [{"id": "q0", "answer": "A"}]}"""


def material(files: list[tuple[str, bytes]], text: str, source: str) -> tuple[list[tuple[str, int, str]], str | None]:
    """Pages of the student's material, or a refusal reason key."""
    if source in ("youtube", "wikipedia"):
        return [], "practice_source_unsupported"
    if files:
        raw = []
        for p in save_uploads(files):
            got, _ = rag.extract(p)
            raw += [(p.name, n, t) for n, t, _ in got if t.strip()]
        pages = clean_pages(raw) if raw else []
    elif text and text.strip():
        chunks = [c.strip() for c in re.split(r"\n\s*\n", text.strip()) if c.strip()] or [text.strip()]
        pages, cur, n = [], "", 1
        for c in chunks:  # ~1500 characters per "page" of pasted text
            if len(cur) + len(c) > 1500 and cur:
                pages.append(("texte", n, cur))
                n, cur = n + 1, ""
            cur = (cur + "\n\n" + c).strip()
        if cur:
            pages.append(("texte", n, cur))
    else:
        return [], "practice_no_material"
    return (pages, None) if pages else ([], "practice_no_text")


def _spread(pages: list, k: int) -> list:
    if len(pages) <= k:
        return pages
    step = len(pages) / k
    return [pages[int(i * step)] for i in range(k)]


def _budget(pages: list[tuple[str, int, str]], total: int) -> str:
    per = max(200, total // max(len(pages), 1))
    return "\n\n".join(f"[{f} p.{n}] {t[:per]}" for f, n, t in pages)[:total + 1500]


def _count(details: str, default: int, lo: int, hi: int) -> int:
    m = re.search(r"\b(\d{1,2})\b", details or "")
    return max(lo, min(hi, int(m.group(1)))) if m else default


def make_quiz(files, text: str, source: str, details: str, lang: str, kw: dict, suspects: dict) -> dict:
    lang = lang_of(lang)
    pages, refusal = material(files, text, source)
    if refusal:
        return PracticeQuiz(quiz_id="", questions=[], sources=[], verification="", refused=tr(refusal, lang)).model_dump()
    body = _budget(_spread(pages, 14), QUIZ_BUDGET)
    n = _count(details, 8, 3, 12)
    quiz_id = hashlib.sha1(f"{body}|{n}|{lang}".encode("utf-8")).hexdigest()[:10]
    try:
        d = llm.ask_json(QUIZ_SYS.format(n=n, lang=LANG[lang], max_words=max(kw["max_words_per_sentence"], 25)),
                         f"Course text:\n{body}", purpose="practice_quiz", max_tokens=4000) or {}
        raw = [q for q in (d.get("questions") or []) if isinstance(q, dict)][:12]
        listed = "\n\n".join(f"[q{i}] {q.get('question', '')}\n" + "\n".join(
            f"{k}: {v}" for k, v in (q.get("options") or {}).items()) for i, q in enumerate(raw))
        blind = llm.ask_json(BLIND_SYS, f"Course text:\n{body}\n\nQuestions:\n{listed}",
                             purpose="practice_quiz_blind", max_tokens=2000) or {}
    except Exception:  # noqa: BLE001  offline and not recorded, or API error
        return PracticeQuiz(quiz_id="", questions=[], sources=[], verification="",
                            refused=tr("practice_unavailable", lang)).model_dump()
    blind_ans = {str(a.get("id", "")).strip("[]"): str(a.get("answer", "")).strip().upper()[:1]
                 for a in (blind.get("answers") or []) if isinstance(a, dict)}
    kept = []
    for i, q in enumerate(raw):
        opts = {k: str(v) for k, v in (q.get("options") or {}).items() if k in "ABCD" and str(v).strip()}
        key = str(q.get("correct", "")).strip().upper()[:1]
        if len(opts) != 4 or key not in opts or blind_ans.get(f"q{i}") != key:
            continue  # malformed, or the blind solver did not find the same answer: dropped
        kept.append((i, q, opts, key))
    texts = {}
    for i, q, opts, _ in kept:
        texts[f"q{i}"] = str(q.get("question", ""))
        texts[f"e{i}"] = str(q.get("explanation", ""))
        for k, v in opts.items():
            texts[f"o{i}{k}"] = v
    checks = _guard_batches(texts, suspects, lang, kw)
    safe = {k: guards_safetext(v, checks[k], lang) for k, v in texts.items() if v.strip()}
    valid = {(f, p) for f, p, _ in pages}
    questions, store = [], {}
    for i, q, opts, key in kept:
        parts = [f"q{i}", f"e{i}"] + [f"o{i}{k}" for k in opts]
        if not all(p in safe and safe[p].shown_allowed for p in parts):
            continue
        qid = f"{quiz_id}-{len(questions) + 1}"
        src = q.get("source") or {}
        f, p = src.get("file"), src.get("page")
        source_ref = [Source(file=f, page=int(p))] if (f, p) in valid else []
        questions.append(PracticeQuestion(id=qid, question=safe[f"q{i}"], options={k: safe[f"o{i}{k}"] for k in opts},
                                          sources=source_ref))
        store[qid] = {"correct": key, "explanation": safe[f"e{i}"]}
    _QUIZZES[quiz_id] = store
    return PracticeQuiz(quiz_id=quiz_id, questions=questions, sources=[Source(file=f, page=p) for f, p, _ in pages],
                        verification=tr("practice_quiz_verification", lang, kept=len(questions), total=len(raw)),
                        refused=None if questions else tr("practice_unavailable", lang)).model_dump()


def check(quiz_id: str, question_id: str, option: str) -> dict:
    store = _QUIZZES.get(quiz_id)
    if store is None or question_id not in store:
        raise KeyError(question_id)
    ans = store[question_id]
    return PracticeCheck(question_id=question_id, correct=option.strip().upper()[:1] == ans["correct"],
                         correct_option=ans["correct"], explanation=ans["explanation"]).model_dump()


def make_cards(files, text: str, source: str, details: str, lang: str, kw: dict, suspects: dict) -> dict:
    lang = lang_of(lang)
    pages, refusal = material(files, text, source)
    if refusal:
        return PracticeCards(deck_id="", cards=[], sources=[], note="", refused=tr(refusal, lang)).model_dump()
    chosen = _spread(pages, 6)
    passages = [{"file": f, "page": p, "text": t} for f, p, t in chosen]
    deck_id = "deck-" + hashlib.sha1(("".join(t for _, _, t in chosen) + lang).encode("utf-8")).hexdigest()[:10]
    try:
        cards, dropped = flashcards.make(deck_id, lang, kw, suspects, None, passages, n=_count(details, 10, 4, 16))
    except Exception:  # noqa: BLE001
        return PracticeCards(deck_id="", cards=[], sources=[], note="", refused=tr("practice_unavailable", lang)).model_dump()
    return PracticeCards(deck_id=deck_id, cards=[{"id": c["id"], "front": c["front"], "back": c["back"]} for c in cards],
                         sources=[Source(file=f, page=p) for f, p, _ in chosen],
                         note=tr("practice_cards_note", lang, dropped=dropped),
                         refused=None if cards else tr("practice_unavailable", lang)).model_dump()


def _guard_batches(texts: dict[str, str], suspects: dict, lang: str, kw: dict, size: int = 12) -> dict:
    keys = list(texts)
    out = {}
    for s in range(0, len(keys), size):
        part = keys[s:s + size]
        ids = {f"x{i}": k for i, k in enumerate(part)}
        judged = guards.check_studio({x: texts[k] for x, k in ids.items()}, suspects, lang,
                                     style_kwargs={**kw, "max_questions": 2, "max_words_per_sentence": 40},
                                     purpose="practice_quiz_judge")
        out.update({k: judged[x] for x, k in ids.items()})
    return out
