"""Tutor chat ("Ask the tutor"): useful for maths, grounded in the course when possible, closed to anything else.

Order of decisions:
0. Pure arithmetic ("5*8", "combien font 12/4 ?") -> computed exactly by SymPy, no LLM ("computed").
1. A course passage is relevant -> answer ONLY from the passages, with (file p.N) citations ("rag_llm"),
   or the passages themselves if the written answer fails a guard ("rag_extractive").
2. Any other school / maths question -> answer as a tutor ("tutor_llm"), labelled "not from your course",
   checked by the guards (SymPy claims, congruency, style, language) before display.
3. Off topic -> fixed polite refusal ("refusal").

1. Topic gate: maths / course vocabulary or a relevant course passage -> on topic; otherwise one small LLM judge
   (cached) decides; if the judge cannot run (e.g. demo mode cache miss), the question is refused (fail closed).
   Off topic -> a fixed, polite refusal in the student's language. No answer from memory.
2. On topic: retrieve passages (engine/rag.py). The LLM writes a short answer ONLY from those passages, with
   (file p.N) citations; the answer passes the guards (SymPy claims, congruency, style, language). If it fails or
   the LLM is unavailable, the passages themselves are returned (extractive answer).
3. On topic but nothing found in the course files: say so (and suggest the diagnosis); never answer from memory.
All LLM calls go through engine/llm.py, so the demo replays them from the cache.
"""
from __future__ import annotations

import re

from engine import guards, llm, mathcheck as mc, rag, safetext
from engine.contract import ChatAnswer, CourseHit
from engine.i18n import lang_of, t as tr

LANG = {"fr": "French (address the student as \"tu\")", "ar": "Modern Standard Arabic (Arabic script, digits for numbers)",
        "en": "English"}
_SCHOOL = re.compile(
    r"(?i)\b(fractions?|num[ée]rateurs?|d[ée]nominateurs?|nombres?|relatifs?|n[ée]gatifs?|positifs?|calcul\w*|"
    r"additionn\w*|addition|soustr\w*|multipli\w*|divis\w*|[ée]quation|[ée]quivalent\w*|simplifi\w*|"
    r"math\w*|cours|le[çc]on|exercice|devoir|"
    r"numerators?|denominators?|numbers?|negative|subtract\w*|add\w*|multipl\w*|equivalent|lesson|homework|"
    r"physique|physics|pendule|pendulum|force|vitesse|speed|"
    r"th[ée]or[èe]mes?|pythagore|thal[èe]s|degr[ée]|discriminant|polyn[ôo]mes?|in[ée]quations?|fonctions?|"
    r"d[ée]riv[ée]e?s?|int[ée]grales?|primitives?|limites?|suites?|g[ée]om[ée]trie|triangles?|rectangles?|"
    r"cercles?|carr[ée]s?|racines?|puissances?|identit[ée]s?\s+remarquables?|factoris\w*|d[ée]velopp\w*|"
    r"aires?|p[ée]rim[èe]tres?|volumes?|angles?|vecteurs?|probabilit[ée]s?|statistiques?|moyenne|m[ée]diane|"
    r"pourcentages?|proportionnalit[ée]|trigonom[ée]trie|cosinus|sinus|tangente|hypot[ée]nuse|parall[èe]le|"
    r"perpendiculaire|alg[èe]bre|arithm[ée]tique|pgcd|ppcm|nombres? premiers?|logarithmes?|exponentielle|matrices?|"
    r"theorems?|quadratic|polynomials?|inequalit\w*|functions?|derivatives?|integrals?|geometry|circles?|"
    r"squares?|roots?|powers?|percent\w*|probabilit\w*|statistics|algebra|trigonometry|hypotenuse|vectors?)\b"
    r"|كسر|كسور|بسط|مقام|عدد|أعداد|سالب|جمع|طرح|ضرب|قسمة|معادلة|رياضيات|درس|تمرين|مبرهنة|فيثاغورس|طالس|مثلث|"
    r"دائرة|زاوية|مساحة|محيط|جذر|قوة|دالة|مشتقة|احتمال|هندسة|متراجحة|حدودية"
    r"|\d\s*[/+×x*÷-]\s*\d")

JUDGE_SYS = """Decide if a student's message is a question about school learning (maths, sciences, a lesson,
homework, how to study). Greetings, sports, celebrities, games, personal or unsafe topics are NOT.
Return JSON: {"school": true|false}"""
ANSWER_SYS = """You are a calm maths tutor. First decide if the course passages below really explain what the student
asks ("covered"). If covered, answer in {lang} using ONLY the passages; after each sentence that uses a passage,
copy that passage's label exactly, e.g. (cours.pdf p.2). Maths as plain text with digits, no LaTeX; every equality
must be true; at most {max_words} words per sentence; no praise, no exclamation marks; under 90 words.
If not covered, return covered false and an empty answer.
Return JSON: {{"covered": true, "answer": "..."}}"""


TRANSLATE_SYS = """Translate the student's school question into French, keeping every number and symbol.
Return JSON: {"fr": "..."}"""


def _short(file: str) -> str:
    return file.rsplit("/", 1)[-1]


def _fix_citations(text: str, hits: list[dict]) -> str:
    """Replace a generic '(file p.N)' the model may copy from the instructions by the real file name."""
    by_page = {h["page"]: _short(h["file"]) for h in hits}
    return re.sub(r"\((?:file|fichier)\s+p\.?\s*(\d+)\)",
                  lambda m: f"({by_page.get(int(m.group(1)), _short(hits[0]['file']))} p.{m.group(1)})", text)


TUTOR_SYS = """You are a calm maths and science tutor for a school student. Answer in {lang}, clearly and briefly
(under 90 words): give the method step by step, then the result. Maths as plain text with digits, no LaTeX; every
equality must be true; at most {max_words} words per sentence; no praise, no exclamation marks. If the question is
not about school learning, answer only: OFF_TOPIC.
Return JSON: {{"answer": "..."}}"""

_CONCEPT = re.compile(
    r"(?i)(expli\w*|c'?est quoi|qu'?est[- ]ce|d[ée]fini\w*|que (veut dire|signifie)|[àa] quoi sert|"
    r"comment (on |je |faire |r[ée]sou\w*|calcul\w*|trouv\w*|utilis\w*|d[ée]montr\w*)|pourquoi|th[ée]or[èe]me|"
    r"propri[ée]t[ée]|formule|r[èe]gle|m[ée]thode|explain|what (is|are|does)|define|definition|how (do|does|to|can)|"
    r"why|theorem|formula|rule|اشرح|ما هو|ما هي|ماذا يعني|عرف|كيف|لماذا|مبرهنة|قاعدة)")

EXPLAIN_SYS = """You are a patient maths teacher. The student asks a general course question (a notion, a theorem,
a method). Explain it in {lang} like a good teacher, even if it is not in their course files. Use Markdown with
exactly these bold headings, each on its own line, in the student's language:
**{h_idea}** (2-3 short sentences: what it is, when we use it),
**{h_rule}** (the formula or the statement, plain text maths with digits, e.g. a² + b² = c², x = (-b ± √Δ) / (2a)),
**{h_method}** (a numbered list of 2-4 steps; mention the cases when they matter, e.g. the sign of Δ),
**{h_example}** (one fully worked example with small numbers, each step on its own line, every equality true),
**{h_mistake}** (one common mistake and why it is wrong).
Decimals with a comma in French and Arabic (3,14). No LaTeX, no emoji, no praise, no exclamation marks. Every sentence at most {max_words} words and ends with a full
stop. Under 230 words in total. Do not solve the student's current exercise (if given below): use other numbers.
If the question is not about school learning, answer only: OFF_TOPIC.
Return JSON: {{"answer": "..."}}"""

HEADINGS = {
    "fr": dict(h_idea="L'idée", h_rule="La règle", h_method="La méthode", h_example="Exemple",
               h_mistake="Erreur fréquente"),
    "en": dict(h_idea="The idea", h_rule="The rule", h_method="The method", h_example="Example",
               h_mistake="Common mistake"),
    "ar": dict(h_idea="الفكرة", h_rule="القاعدة", h_method="الطريقة", h_example="مثال", h_mistake="خطأ شائع"),
}


def is_concept(question: str) -> bool:
    """A general course question ("explique-moi ...", "c'est quoi le théorème de ...") rather than a calculation."""
    return bool(_CONCEPT.search(question))


_EXPR = re.compile(r"[-(]*\d[\d\s+\-*/×÷x:().,^]*[\d)]")
_FILLER = re.compile(r"(?i)\b(combien|font|fait|faire|calcule[rz]?|calcul|quel(?:le)?|est|vaut|c'est|ça|égal|égale|"
                     r"what|is|how|much|calculate|compute|equals?|كم|يساوي|احسب)\b|[=?؟:!]")


def arithmetic(question: str) -> tuple[str, str] | None:
    """'5*8', 'combien font 12/4 ?' -> (expression, exact value) computed by SymPy; None if not pure arithmetic."""
    m = max(_EXPR.findall(question), key=len, default="")
    if not m or not re.search(r"[+\-*/×÷x:^]", m.strip("-( ")):
        return None
    rest = _FILLER.sub(" ", question.replace(m, " "))
    if len(re.findall(r"\w+", rest)) > 1:
        return None  # there is more to the question than the calculation
    expr = m.strip().replace("x", "*").replace(":", "/").replace("^", "**").replace(",", ".")
    v = mc.value(expr)
    if v is None or getattr(v, "free_symbols", None):
        return None
    pretty = m.strip().replace("*", " × ").replace("/", " / ")
    pretty = re.sub(r"\s+", " ", pretty)
    try:
        import sympy as sp
        val = sp.nsimplify(v)
        out = str(val) if val.is_Rational else str(sp.N(val, 8)).rstrip("0").rstrip(".")
        if val.is_Rational and val.q != 1:
            out += f" ≈ {float(val):.4g}"
    except Exception:  # noqa: BLE001
        out = str(v)
    return pretty, out


def on_topic(question: str, hits: list[dict] | None = None) -> tuple[bool, str]:
    """Maths / school vocabulary -> on topic; otherwise the LLM judge. A retrieved page never decides: embeddings
    find weak similarities ("Cristiano Ronaldo" scored close to a thermodynamics slide)."""
    if _SCHOOL.search(question):
        return True, "keywords"
    try:
        d = llm.ask_json(JUDGE_SYS, question, purpose="chat_topic", max_tokens=256) or {}
        return bool(d.get("school")), "llm judge"
    except Exception:  # noqa: BLE001  fail closed: refuse
        return False, "judge unavailable"


def answer(question: str, lang: str, kw: dict, suspects: dict[str, str], exercise: dict | None = None) -> dict:
    lang = lang_of(lang)
    question = (question or "").strip()
    if not question:
        raise ValueError("empty question")
    calc = arithmetic(question)
    if calc:
        return ChatAnswer(question=question, on_topic=True, method="computed", topic_reason="arithmetic",
                          label=tr("chat_label_computed", lang),
                          answer=safetext.static(f"{calc[0]} = {calc[1]}", lang=lang), citations=[]).model_dump()
    ix = rag.index()
    hits = [h for h in ix.search(question, 3) if h["relevant"]] if ix.chunks else []
    if not hits and ix.chunks and lang == "ar":
        # courses are often in French: search with a French translation of the question (cached LLM call)
        try:
            fr = str((llm.ask_json(TRANSLATE_SYS, question, purpose="chat_translate_query", max_tokens=256) or {})
                     .get("fr", "")).strip()
            hits = [h for h in ix.search(fr, 3) if h["relevant"]] if fr else []
        except Exception:  # noqa: BLE001
            pass
    ok, why = on_topic(question)
    cites = [CourseHit(folder=h["folder"], file=h["file"], page=h["page"], snippet=rag.snippet(h["text"], question),
                       lang=h["lang"], source_url=h["source_url"], allow_derivatives=h["allow_derivatives"],
                       score=h["score"]) for h in hits]
    if not ok:
        return ChatAnswer(question=question, on_topic=False, method="refusal", topic_reason=why,
                          answer=safetext.static(tr("chat_refusal", lang), lang=lang), citations=[]).model_dump()
    if not hits or (is_concept(question) and not _covers(question, hits)):
        return tutor_answer(question, lang, kw, suspects, why, exercise)
    passages = "\n".join(f"[({_short(h['file'])} p.{h['page']})] {h['text'][:1200]}" for h in hits)
    try:
        d = llm.ask_json(ANSWER_SYS.format(lang=LANG[lang], max_words=kw["max_words_per_sentence"]),
                         f"Course passages:\n{passages}\n\nStudent question: {question}",
                         purpose="chat_answer", max_tokens=1024) or {}
        if d.get("covered") is False:
            return tutor_answer(question, lang, kw, suspects, why, exercise)  # passages found, but they do not answer it
        text = _fix_citations(str(d.get("answer", "")).strip(), hits)
        checks = guards.check_studio({"a": text}, suspects, lang, style_kwargs={**kw, "max_questions": 2},
                                     purpose="chat_answer_judge")["a"] if text else None
    except Exception:  # noqa: BLE001
        text, checks = "", None
    if text and checks and not any(c.status == "fail" for c in checks):
        return ChatAnswer(question=question, on_topic=True, method="rag_llm", topic_reason=why,
                          label=tr("chat_label_course", lang),
                          answer=safetext.from_guards(text, checks, lang=lang), citations=cites).model_dump()
    # extractive fallback: the passages themselves (not rewritten), with their pages
    lines = [tr("chat_extractive", lang)] + [f"« {c.snippet} » ({c.file}, p. {c.page})" for c in cites]
    return ChatAnswer(question=question, on_topic=True, method="rag_extractive", topic_reason=why,
                      label=tr("chat_label_course", lang),
                      answer=safetext.static("\n".join(lines), lang=lang,
                                             style_kwargs={"max_words_per_sentence": 200, "neutral": False}),
                      citations=cites).model_dump()


_STOP = {"explique", "expliquer", "explique-moi", "c'est", "quoi", "qu'est-ce", "comment", "pourquoi", "théorème",
         "theoreme", "formule", "méthode", "methode", "règle", "regle", "propriété", "définition", "explain", "what",
         "define", "definition", "theorem", "formula", "method", "about", "avec", "dans", "pour", "faire", "calculer"}


def _covers(question: str, hits: list[dict]) -> bool:
    """A concept question is 'covered' only if its own key words (e.g. 'pythagore', 'degré') are in the passages."""
    words = [w for w in re.findall(r"[\wÀ-ÿ']+", question.lower()) if len(w) >= 5 and w not in _STOP]
    text = " ".join(h["text"].lower() for h in hits)
    return bool(words) and any(w in text for w in words)


def _leak_check(text: str, exercise: dict | None) -> list[str]:
    """The chat never gives away the answer of the exercise the student is working on."""
    return guards.deterministic_leak(text, exercise) if exercise else []


def tutor_answer(question: str, lang: str, kw: dict, suspects: dict[str, str], why: str,
                 exercise: dict | None = None) -> dict:
    """School question not covered by the course files: a guarded tutor answer, labelled as not from the course.
    A general course question ("explique-moi ...") gets a structured teacher explanation with a worked example."""
    concept = is_concept(question)
    try:
        if concept:
            ex = f"\n\nThe student's current exercise (do NOT solve it): {exercise['text']}" if exercise else ""
            sys = EXPLAIN_SYS.format(lang=LANG[lang], max_words=max(kw["max_words_per_sentence"], 25),
                                     **HEADINGS[lang])
            d = llm.ask_json(sys, question + ex, purpose="chat_explain", max_tokens=2048) or {}
        else:
            d = llm.ask_json(TUTOR_SYS.format(lang=LANG[lang], max_words=max(kw["max_words_per_sentence"], 25)),
                             question, purpose="chat_tutor", max_tokens=1024) or {}
        text = str(d.get("answer", "")).strip()
        if not text or "OFF_TOPIC" in text:
            return ChatAnswer(question=question, on_topic=False, method="refusal", topic_reason="llm tutor",
                              answer=safetext.static(tr("chat_refusal", lang), lang=lang), citations=[]).model_dump()
        checks = guards.check_studio({"a": text}, suspects, lang,
                                     style_kwargs={**kw, "max_questions": 3 if concept else 2,
                                                   "max_words_per_sentence": 40},
                                     purpose="chat_explain_judge" if concept else "chat_tutor_judge")["a"]
        leak = _leak_check(text, exercise)
        checks = [c if c.name != "leak" else c.model_copy(update={
            "status": "fail" if leak else "pass", "detail": "; ".join(leak) or "current exercise not revealed"})
                  for c in checks] if exercise else checks
        if not any(c.status == "fail" for c in checks):
            return ChatAnswer(question=question, on_topic=True, method="tutor_explain" if concept else "tutor_llm",
                              topic_reason=why, label=tr("chat_label_tutor", lang),
                              answer=safetext.from_guards(text, checks, lang=lang), citations=[]).model_dump()
    except Exception:  # noqa: BLE001  offline and not cached, or API error
        pass
    return ChatAnswer(question=question, on_topic=True, method="not_found", topic_reason=why,
                      answer=safetext.static(tr("chat_unavailable", lang), lang=lang), citations=[]).model_dump()
