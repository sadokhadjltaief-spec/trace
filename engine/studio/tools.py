"""Study Studio dispatcher and tools other than flashcards."""
from __future__ import annotations

import json

from engine import guards, i18n, llm, mathcheck as mc, rag, safetext
from engine.contract import MisconceptionView, OutputFile, Source, StudioOutput
from engine.studio import diagrams, export_dir, flashcards, rel
from engine.studio.pdf import Doc

T = {  # fixed headings (our wording; FR/AR to be checked by a native speaker)
    "targeted": {"en": "Targeted at", "fr": "Ciblé sur", "ar": "موجّه إلى"},
    "key": {"en": "Key idea", "fr": "Idée clé", "ar": "الفكرة الأساسية"},
    "mistake": {"en": "Common mistake", "fr": "Erreur fréquente", "ar": "خطأ شائع"},
    "example": {"en": "Worked example", "fr": "Exemple corrigé", "ar": "مثال محلول"},
    "formulas": {"en": "Key formulas", "fr": "Formules clés", "ar": "صيغ أساسية"},
    "practice": {"en": "Practice", "fr": "Entraînement", "ar": "تمرين"},
    "answers": {"en": "Answer key", "fr": "Corrigé", "ar": "الإجابات"},
    "sources": {"en": "Sources", "fr": "Sources", "ar": "المصادر"},
    "wrong_step": {"en": "wrong step", "fr": "étape fausse", "ar": "خطوة خاطئة"},
    "correct_answer": {"en": "Correct answer", "fr": "Bonne réponse", "ar": "الإجابة الصحيحة"},
    "bank": {"en": "TRACE question bank (human-verified)", "fr": "Banque de questions TRACE (vérifiée par un humain)",
             "ar": "بنك أسئلة TRACE (تحقّق منه إنسان)"},
    "refused": {"en": "This folder does not allow derived material (allow_derivatives: false). TRACE can only cite it.",
                "fr": "Ce dossier n'autorise pas de contenu dérivé (allow_derivatives: false). TRACE peut seulement le citer.",
                "ar": "هذا المجلّد لا يسمح بمحتوى مشتقّ (allow_derivatives: false). يمكن لـ TRACE الاستشهاد به فقط."},
    "no_diag": {"en": "No diagnosis yet: finish a diagnosis first, or choose course pages.",
                "fr": "Pas encore de diagnostic : termine d'abord un diagnostic, ou choisis des pages de cours.",
                "ar": "لا يوجد تشخيص بعد: أنهِ التشخيص أولًا، أو اختر صفحات من الدروس."},
}
LANG = {"fr": "French (address the student as \"tu\")", "ar": "Modern Standard Arabic (Arabic script, digits for numbers)",
        "en": "English"}

SUMMARY_SYS = """Write a short revision sheet in {lang} for a school student.
{goal}
Sections (JSON keys): "key_idea" (2-3 sentences), "common_mistake" (2 sentences: the wrong idea and why it fails),
"example" (one short worked example with different numbers, every equality true), "formulas" (0-3 short lines).
Maths as plain text with digits, no LaTeX. Sentences of at most {max_words} words. No praise, no "!".
Return JSON: {{"key_idea": "...", "common_mistake": "...", "example": "...", "formulas": ["..."]}}"""


def t(key: str, lang: str) -> str:
    return T[key].get(lang) or T[key]["en"]


def _passages(source: dict, query: str) -> tuple[list[dict], str | None]:
    """Course chunks for kind folder/pages. Returns (passages, refusal reason or None)."""
    kind = source.get("kind", "diagnosis")
    if kind == "diagnosis":
        return [], None
    ix = rag.index()
    if kind == "folder":
        chunks = [c for c in ix.chunks if c.folder == source.get("folder")]
    else:
        want = {(p["file"], int(p["page"])) for p in source.get("pages", [])}
        chunks = [c for c in ix.chunks if (c.file, c.page) in want]
    if any(not c.allow_derivatives for c in chunks):
        return [], "refused"
    if source.get("folder") and not rag.folder_meta(rag.COURSES / source["folder"]).get("allow_derivatives", False):
        return [], "refused"
    if kind == "folder" and query:
        hits = [h for h in ix.search(query, 6) if h["folder"] == source.get("folder")]
        chunks = [c for c in chunks if any(h["file"] == c.file and h["page"] == c.page for h in hits)] or chunks
    return [{"file": c.file, "page": c.page, "text": c.text} for c in chunks[:4]], None


def summary_sections(mis: dict | None, lang: str, kw: dict, passages: list[dict], suspects: dict) -> dict:
    """LLM revision sheet (cached), every section guarded. Unsafe sections are dropped, not shown."""
    if passages:
        goal = ("Use ONLY these course passages; after each sentence that uses a passage, add its citation like "
                "(file p.N).\n" + "\n".join(f"[{p['file']} p.{p['page']}] {p['text'][:900]}" for p in passages))
        if mis:
            goal += f"\nThe common mistake section is about: {mis['name_en']}."
    else:
        goal = f"Topic: the misconception \"{mis['name_en']}\" ({mis.get('description', '')})."
    d = llm.ask_json(SUMMARY_SYS.format(lang=LANG.get(lang, "English"), goal=goal,
                                        max_words=kw["max_words_per_sentence"]),
                     "Write the sheet now.", purpose="studio_summary", max_tokens=2048) or {}
    texts = {k: str(d.get(k, "")).strip() for k in ("key_idea", "common_mistake", "example")}
    for i, f in enumerate(d.get("formulas") or []):
        texts[f"formula{i}"] = str(f).strip()
    texts = {k: v for k, v in texts.items() if v}
    checks = guards.check_studio(texts, suspects, lang, style_kwargs={**kw, "max_questions": 2},
                                 purpose="studio_summary_judge")
    return {k: flashcards.guards_safetext(v, checks[k], lang) for k, v in texts.items()}


def worksheet(qs: list[dict], lang: str, title: str, doc: Doc | None = None) -> Doc:
    """Questions on page 1, answer key on page 2 (answer keys come from the verified bank)."""
    doc = doc or Doc(title)
    doc.heading(t("practice", lang))
    for n, q in enumerate(qs, 1):
        text, opts = i18n.question(q, lang)
        doc.text(f"{n}. {mc.latex_to_plain(text)}")
        doc.text("    " + "    ".join(f"{k}) {mc.latex_to_plain(v)}" for k, v in opts.items()), gap=3)
    doc.page()
    doc.heading(t("answers", lang))
    for n, q in enumerate(qs, 1):
        _, opts = i18n.question(q, lang)
        doc.text(f"{n}. {q['correct']}) {mc.latex_to_plain(opts[q['correct']])}")
    return doc


def slides(path, mis_view: dict, lang: str, sections: dict, recon: dict | None, qs: list[dict], diagram_png,
           sources: list[str]):
    """python-pptx deck (6-10 slides); Arabic paragraphs right-to-left."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.33), Inches(7.5)
    teal = RGBColor(0x0F, 0x76, 0x6E)
    rtl = lang == "ar"

    def add(title: str, lines: list[str], image=None):
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = title
        s.shapes.title.text_frame.paragraphs[0].runs[0].font.color.rgb = teal
        box = s.shapes.add_textbox(Inches(0.7), Inches(1.6), Inches(6.2 if image else 11.9), Inches(5.3))
        tf = box.text_frame
        tf.word_wrap = True
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.font.size = Pt(22)
            if rtl:
                p._p.get_or_add_pPr().set("rtl", "1")
        if image:
            s.shapes.add_picture(str(image), Inches(7.1), Inches(1.8), width=Inches(5.8))
        return s

    name = {"fr": mis_view.get("name_fr"), "ar": mis_view.get("name_ar")}.get(lang) or mis_view["name_en"]
    add("TRACE", [f"{t('targeted', lang)}: {name}"])
    if "key_idea" in sections:
        add(t("key", lang), [sections["key_idea"].text])
    if "common_mistake" in sections:
        add(t("mistake", lang), [sections["common_mistake"].text], image=diagram_png)
    if recon:
        problem, steps = i18n.reconstruction(recon, lang)
        add(t("example", lang), [problem] + [f"{i}. {s}" + (f"  ({t('wrong_step', lang)})" if i == recon["error_step"] else "")
                                             for i, s in enumerate(steps, 1)]
            + [f"{t('correct_answer', lang)}: {recon.get('correct_answer', '')}"])
    if "example" in sections:
        add(t("example", lang), [sections["example"].text])
    if qs:
        text, opts = i18n.question(qs[0], lang)
        add(t("practice", lang), [mc.latex_to_plain(text)] + [f"{k}) {mc.latex_to_plain(v)}" for k, v in opts.items()])
    formulas = [v.text for k, v in sections.items() if k.startswith("formula")]
    if formulas:
        add(t("formulas", lang), formulas)
    add(t("sources", lang), sources)
    prs.save(str(path))
    return path


def generate(session: dict, session_id: str, tool: str, source: dict, mis_view: dict | None, mis: dict | None,
             lang: str, kw: dict, bank: dict, suspects: dict) -> dict:
    """All tools. `mis_view` = the diagnosed misconception (None if no diagnosis)."""
    targeted = MisconceptionView(**mis_view) if mis_view else None
    query = " ".join(x for x in ((mis_view or {}).get("name_fr"), (mis_view or {}).get("name_en"),
                                 (mis or {}).get("description")) if x)
    passages, refusal = _passages(source or {}, query)
    if refusal:
        return StudioOutput(session_id=session_id, tool=tool, targeted_at=targeted, sources=[], files=[], items=[],
                            refused=t("refused", lang)).model_dump()
    if not mis and not passages and tool != "quiz":
        return StudioOutput(session_id=session_id, tool=tool, targeted_at=None, sources=[], files=[], items=[],
                            refused=t("no_diag", lang)).model_dump()
    out_dir = export_dir(session_id)
    srcs = [Source(file=p["file"], page=p["page"]) for p in passages] or [Source(file=t("bank", lang))]
    src_lines = [f"{s.file}" + (f", p. {s.page}" if s.page else "") for s in srcs]
    h = (mis or {}).get("id")
    qs = [q for q in bank["questions"] if q.get("verified") and (not h or q.get("target") == h)][:4]
    recon = next((r for r in bank.get("reconstruction", []) if r.get("verified") and r["misconception"] == h), None)
    files, items = [], []
    if tool == "flashcards":
        cards, dropped = flashcards.make(session_id, lang, kw, suspects, mis, passages)
        files = flashcards.export(session_id, out_dir, [{"id": c["id"], "front": c["front"]["text"],
                                                          "back": c["back"]["text"]} for c in cards])
        items = cards
        if dropped:
            items = items + [{"dropped_by_guards": dropped}]
    elif tool == "diagram":
        png = diagrams.draw(h, out_dir / f"diagram_{h}.png", lang)
        files = [(png, "image/png")]
        items = [{"image": rel(png), "caption": safetext.static(f"{t('targeted', lang)}: {mis_view['name_en']}",
                                                               lang="en").model_dump()}]
    elif tool == "quiz":
        items = [{"question_id": q["id"], "text": i18n.question(q, lang)[0], "options": i18n.question(q, lang)[1]}
                 for q in qs]
        doc = Doc("TRACE quiz")
        if targeted:
            doc.title(f"{t('targeted', lang)}: {mis_view.get('name_' + lang) or mis_view['name_en']}")
        pdf = worksheet(qs, lang, "TRACE quiz", doc).save(out_dir / "worksheet.pdf")
        files = [(pdf, "application/pdf")]
    else:  # summary, slides, pdf: need the guarded revision sheet
        sections = summary_sections(mis, lang, kw, passages, suspects)
        items = [{"section": k, "text": v.model_dump()} for k, v in sections.items()]
        shown = {k: v for k, v in sections.items() if v.shown_allowed}
        name = (mis_view or {}).get("name_" + lang) or (mis_view or {}).get("name_en", "")
        if tool in ("summary", "pdf"):
            md = [f"# TRACE", f"**{t('targeted', lang)}: {name}**" if mis_view else ""]
            for key, head in (("key_idea", "key"), ("common_mistake", "mistake"), ("example", "example")):
                if key in shown:
                    md += [f"## {t(head, lang)}", shown[key].text]
            fl = [v.text for k, v in shown.items() if k.startswith("formula")]
            if fl:
                md += [f"## {t('formulas', lang)}"] + [f"- {f}" for f in fl]
            md += [f"## {t('sources', lang)}"] + [f"- {s}" for s in src_lines]
            mdp = out_dir / "summary.md"
            mdp.write_text("\n\n".join(x for x in md if x), encoding="utf-8")
            doc = Doc("TRACE summary")
            for line in md:
                if line.startswith("# "):
                    doc.title(line[2:])
                elif line.startswith("## "):
                    doc.heading(line[3:])
                elif line:
                    doc.text(line.replace("**", ""))
            if tool == "pdf" and h in ("M1", "M2", "M3", "M4"):
                doc.image(diagrams.draw(h, out_dir / f"diagram_{h}.png", lang))
                doc.page()
                worksheet(qs, lang, "TRACE", doc)
            pdf = doc.save(out_dir / ("summary.pdf" if tool == "summary" else "trace_sheet.pdf"))
            files = [(mdp, "text/markdown"), (pdf, "application/pdf")]
        else:
            png = diagrams.draw(h, out_dir / f"diagram_{h}.png", lang) if h in ("M1", "M2", "M3", "M4") else None
            deck = slides(out_dir / "slides.pptx", mis_view or {"name_en": ""}, lang, shown, recon, qs, png, src_lines)
            files = [(deck, "application/vnd.openxmlformats-officedocument.presentationml.presentation")]
    return StudioOutput(session_id=session_id, tool=tool, targeted_at=targeted, sources=srcs,
                        files=[OutputFile(path=rel(p), mime=m) for p, m in files], items=items).model_dump()


__all__ = ["generate", "json"]
