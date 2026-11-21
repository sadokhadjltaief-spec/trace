"""Flashcards: LLM drafts targeted at the diagnosed misconception (or from course passages, cited), guarded
(SymPy claims, congruency, style, language), stored as UNVERIFIED until a human approves them (review screen).
Leitner boxes in SQLite; a lapse ("again") on a misconception card is evidence for that misconception.
Exports: Anki .apkg (genanki) and TSV."""
from __future__ import annotations

import hashlib
import json
import time

from engine import guards, llm, style
from engine.contract import Check, SafeText

BOX_DAYS = {1: 0, 2: 1, 3: 3, 4: 7, 5: 14}
LANG = {"fr": "French (address the student as \"tu\")", "ar": "Modern Standard Arabic (Arabic script, digits for numbers)",
        "en": "English"}

CARDS_SYS = """You write {n} flashcards in {lang} for a school student.
{goal}
Rules: maths as plain text with digits (1/3, 2 x 5, -7), no LaTeX; every equality must be true; short sentences
(at most {max_words} words each); no praise words, no exclamation marks, no emoji.
Return JSON: {{"cards": [{{"front": "...", "back": "..."}}]}}"""
GOAL_MIS = ("The student holds this misconception: \"{name}\" ({description}). Each FRONT is a short question that "
            "would tempt this wrong idea. Each BACK gives the correct reasoning and result, and one sentence saying "
            "why the wrong idea fails.")
GOAL_CHUNKS = ("Make definition or formula cards ONLY from these course passages; do not add facts that are not in "
               "them. Put the citation given before each passage at the end of the back, like (file p.N).\n{passages}")


def _db():
    con = llm._db()
    con.execute("""CREATE TABLE IF NOT EXISTS cards(id TEXT PRIMARY KEY, session TEXT, misconception TEXT,
        lang TEXT, front TEXT, back TEXT, front_checks TEXT, back_checks TEXT, source TEXT, verified INTEGER,
        box INTEGER, due REAL, lapses INTEGER, created REAL)""")
    return con


def draft(n: int, lang: str, kw: dict, mis: dict | None = None, passages: list[dict] | None = None) -> list[dict]:
    if passages:
        txt = "\n".join(f"[{p['file']} p.{p['page']}] {p['text'][:900]}" for p in passages)
        goal = GOAL_CHUNKS.format(passages=txt)
    else:
        goal = GOAL_MIS.format(name=mis["name_en"], description=mis.get("description", ""))
    sysmsg = CARDS_SYS.format(n=n, lang=LANG.get(lang, "English"), goal=goal, max_words=kw["max_words_per_sentence"])
    d = llm.ask_json(sysmsg, "Write the cards now.", purpose="studio_flashcards", max_tokens=2048)
    return [c for c in (d or {}).get("cards", []) if isinstance(c, dict) and c.get("front") and c.get("back")][:n]


def make(session_id: str, lang: str, kw: dict, suspects: dict[str, str], mis: dict | None,
         passages: list[dict] | None = None, n: int = 4) -> tuple[list[dict], int]:
    """Draft, guard, store. Returns (cards that passed every check, number dropped by the guards)."""
    raw = draft(n, lang, kw, mis, passages)
    texts = {}
    for i, c in enumerate(raw):
        texts[f"f{i}"], texts[f"b{i}"] = str(c["front"]), str(c["back"])
    # the judge sees each card as ONE text (question + answer), so a front and its back cannot be merged or lost
    cards = {f"c{i}": texts[f"f{i}"] + "\n" + texts[f"b{i}"] for i in range(len(raw))}
    judged = guards.check_studio(cards, suspects, lang, style_kwargs={**kw, "max_questions": 2},
                                 purpose="studio_flashcards_judge") if cards else {}
    checks = {}
    for i in range(len(raw)):
        semantic = [c for c in judged[f"c{i}"] if c.name in ("leak", "math", "congruency")]
        for side in ("f", "b"):  # style + language on each side
            viol = style.lint(texts[f"{side}{i}"], **{**kw, "max_questions": 2})
            wl = guards.language_check(texts[f"{side}{i}"], lang)
            viol += [wl] if wl else []
            checks[f"{side}{i}"] = semantic + [Check(name="style", status="fail" if viol else "pass",
                                                     detail="; ".join(viol))]
    kept, dropped = [], 0
    con = _db()
    for i, c in enumerate(raw):
        fc, bc = checks[f"f{i}"], checks[f"b{i}"]
        front = guards_safetext(texts[f"f{i}"], fc, lang)
        back = guards_safetext(texts[f"b{i}"], bc, lang)
        if not (front.shown_allowed and back.shown_allowed):
            dropped += 1
            continue
        cid = hashlib.sha1(f"{session_id}|{texts[f'f{i}']}".encode()).hexdigest()[:12]
        src = json.dumps([{"file": p["file"], "page": p["page"]} for p in (passages or [])])
        con.execute("INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, session_id, (mis or {}).get("id"), lang, front.text, back.text,
                     json.dumps([x.model_dump() for x in fc]), json.dumps([x.model_dump() for x in bc]), src,
                     0, 1, time.time(), 0, time.time()))
        kept.append({"id": cid, "front": front.model_dump(), "back": back.model_dump(), "verified": False,
                     "misconception": (mis or {}).get("id"), "box": 1})
    con.commit()
    con.close()
    return kept, dropped


def guards_safetext(text: str, checks: list[Check], lang: str) -> SafeText:
    ok = {"leak", "congruency", "math", "style"} <= {c.name for c in checks} and not any(
        c.status == "fail" for c in checks)
    return SafeText(text=text, lang=lang if lang in ("fr", "ar", "en") else "en", origin="llm", checks=checks,
                    shown_allowed=ok)


def rows(session_id: str, verified_only: bool = False) -> list[dict]:
    con = _db()
    q = "SELECT id, misconception, lang, front, back, front_checks, back_checks, source, verified, box, due, lapses " \
        "FROM cards WHERE session = ?" + (" AND verified = 1" if verified_only else "") + " ORDER BY created"
    out = []
    for r in con.execute(q, (session_id,)).fetchall():
        out.append({"id": r[0], "misconception": r[1], "lang": r[2], "front": r[3], "back": r[4],
                    "front_checks": json.loads(r[5]), "back_checks": json.loads(r[6]), "sources": json.loads(r[7]),
                    "verified": bool(r[8]), "box": r[9], "due": r[10], "lapses": r[11]})
    con.close()
    return out


def verify(card_id: str, ok: bool) -> None:
    """Human review: approve (verified) or reject (deleted) a drafted card."""
    con = _db()
    if ok:
        con.execute("UPDATE cards SET verified = 1 WHERE id = ?", (card_id,))
    else:
        con.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    con.commit()
    con.close()


def review(card_id: str, rating: str, now: float | None = None) -> dict:
    """Leitner: again -> box 1, hard -> same box, good -> +1, easy -> +2 (max 5). Only verified cards."""
    if rating not in ("again", "hard", "good", "easy"):
        raise ValueError("rating must be again / hard / good / easy")
    now = now or time.time()
    con = _db()
    r = con.execute("SELECT box, lapses, verified, misconception FROM cards WHERE id = ?", (card_id,)).fetchone()
    if not r:
        con.close()
        raise KeyError(card_id)
    box, lapses, verified, mis = r
    if not verified:
        con.close()
        raise ValueError("card not verified yet (human review first)")
    box = {"again": 1, "hard": box, "good": min(box + 1, 5), "easy": min(box + 2, 5)}[rating]
    lapses += rating == "again"
    due = now + BOX_DAYS[box] * 86400
    con.execute("UPDATE cards SET box = ?, due = ?, lapses = ? WHERE id = ?", (box, due, lapses, card_id))
    con.commit()
    con.close()
    return {"id": card_id, "box": box, "due": due, "lapse": rating == "again", "misconception": mis}


def due(session_id: str, now: float | None = None) -> list[dict]:
    now = now or time.time()
    return [c for c in rows(session_id, verified_only=True) if c["due"] <= now]


def export(session_id: str, out_dir, cards: list[dict]) -> list:
    import genanki
    tsv = out_dir / "flashcards.tsv"
    tsv.write_text("\n".join(f"{c['front'].replace(chr(9), ' ')}\t{c['back'].replace(chr(9), ' ')}" for c in cards),
                   encoding="utf-8")
    model = genanki.Model(1607392319, "TRACE card", fields=[{"name": "Front"}, {"name": "Back"}],
                          templates=[{"name": "Card 1", "qfmt": "{{Front}}",
                                      "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}])
    deck = genanki.Deck(int(hashlib.sha1(session_id.encode()).hexdigest()[:8], 16), f"TRACE {session_id}")
    for c in cards:
        deck.add_note(genanki.Note(model=model, fields=[c["front"], c["back"]], guid=genanki.guid_for(c["id"])))
    apkg = out_dir / "flashcards.apkg"
    genanki.Package(deck).write_to_file(str(apkg))
    return [(apkg, "application/octet-stream"), (tsv, "text/tab-separated-values")]
