"""Build the TRACE question bank (Set A) -> data/bank/bank.json + data/bank/review.md

Usage: .\\.venv\\Scripts\\python.exe eval\\build_bank.py

- Questions come from real data: 4 MAP questions + 10 Eedi questions (chosen by hand, IDs below).
- MAP options/answer key are reconstructed from the MC_Answer values; option->misconception mappings
  are taken from the MAP labels (plurality rule, logged). Eedi mappings come from crosswalk.json.
- Hints (3 levels), worked solutions with one wrong step (RECONSTRUCT) and FR/AR names are drafted by
  the LLM, checked with SymPy, and written to review.md. Nothing is `verified` until a human ticks it
  in review.md ("- [x] <item id>"); re-running this script reads those ticks.
- bank.json and review.md contain Eedi text, so they are local-only (gitignored).
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT  # noqa: E402
from engine import llm, mathcheck as mc  # noqa: E402

RAW = ROOT / "data" / "raw"
BANK = ROOT / "data" / "bank"
LOG: list[str] = []


def log(s=""):
    print(s)
    LOG.append(s)


# ------------------------------------------------------------------ hand-chosen content
# English names/descriptions are written from the MAP explanations and the Eedi labels (see crosswalk.json).
MISCONCEPTIONS = [
    {"id": "M1", "map_label": "Adding_across",
     "name_en": "Adds numerators and adds denominators",
     "description": "To add two fractions, the student adds the tops and adds the bottoms: a/b + c/d = (a+c)/(b+d).",
     "contrast_example": "1/2 + 1/2 would give 2/4 = 1/2, but two halves make one whole, so 1/2 + 1/2 = 1."},
    {"id": "M2", "map_label": "Duplication",
     "name_en": "Multiplies both numerator and denominator by the whole number",
     "description": "To multiply a fraction by a whole number, the student multiplies the top and the bottom: k × a/b = (ka)/(kb).",
     "contrast_example": "2 × 1/2 would give 2/4 = 1/2, but two halves make one whole, so 2 × 1/2 = 1."},
    {"id": "M3", "map_label": "Positive",
     "name_en": "Thinks 'two negatives make a positive' always applies",
     "description": "When a calculation has two minus signs, the student makes the answer positive, e.g. (-8) - (-5) = 3 or 13.",
     "contrast_example": "(-2) - (-1): start at -2 and remove a debt of 1, you get -1, which is still negative."},
    {"id": "M4", "map_label": "Additive",
     "name_en": "Makes equivalent fractions by adding instead of multiplying",
     "description": "To find an equivalent fraction, the student adds the same number to the top and bottom instead of multiplying.",
     "contrast_example": "1/2 -> add 1 to top and bottom -> 2/3, but 2/3 is bigger than 1/2; 1/2 = 2/4 (multiply by 2)."},
]

QUESTIONS = [  # (bank id, source, source question id, target misconception)
    ("Q1", "map", 33472, "M1"), ("Q2", "eedi", 328, "M1"), ("Q3", "eedi", 789, "M1"), ("Q4", "eedi", 1430, "M1"),
    ("Q5", "map", 32833, "M2"), ("Q6", "eedi", 1640, "M2"), ("Q7", "eedi", 266, "M2"),
    ("Q8", "map", 89443, "M3"), ("Q9", "eedi", 860, "M3"), ("Q10", "eedi", 1294, "M3"),
    ("Q11", "map", 31778, "M4"), ("Q12", "eedi", 338, "M4"), ("Q13", "eedi", 987, "M4"), ("Q14", "eedi", 1360, "M4"),
]


# ------------------------------------------------------------------ data -> questions
def map_question(df: pd.DataFrame, qid: int, label_to_m: dict) -> dict:
    s = df[df.QuestionId == qid]
    opts = sorted(s.MC_Answer.unique(), key=lambda x: (mc.value(x) is None, mc.value(x) or 0))
    letters = dict(zip("ABCD", opts))
    inv = {v: k for k, v in letters.items()}
    # correct = option chosen by the True_* rows
    correct_txt = s[s.Category.str.startswith("True")].MC_Answer.value_counts().idxmax()
    om, counts = {}, {}
    for L, txt in letters.items():
        sub = s[s.MC_Answer == txt]
        mis = sub[sub.Category.str.endswith("Misconception")].Misconception.value_counts()
        counts[L] = {"n": int(len(sub)), "true_correct": int((sub.Category == "True_Correct").sum()),
                     "misconceptions": {k: int(v) for k, v in mis.items()}}
        if L == inv[correct_txt]:
            continue
        top = mis.index[0] if len(mis) else None
        om[L] = label_to_m.get(top) if top is not None and mis.iloc[0] >= 10 else None
        log(f"  MAP {qid} option {L} {txt!r}: top label={top} ({int(mis.iloc[0]) if len(mis) else 0}) -> {om[L]}")
    # per-misconception answer distribution (for data-driven likelihoods in bayes.py)
    label_counts = {}
    for lab, m in label_to_m.items():
        sub = s[s.Misconception == lab]
        if len(sub):
            label_counts[m] = {inv[k]: int(v) for k, v in sub.MC_Answer.value_counts().items()}
    # M0 = no labelled misconception (Correct + Neither rows). Using True_Correct only would force
    # P(correct|M0) ~ 1 by construction (selection bias); Neither rows include ordinary slips.
    label_counts["M0"] = {inv[k]: int(v) for k, v in s[s.Misconception.isna()].MC_Answer.value_counts().items()}
    return {"text": s.QuestionText.iloc[0], "options": letters, "correct": inv[correct_txt],
            "option_misconception": om, "map_question_id": int(qid), "source": "map", "local_only": False,
            "map_option_counts": counts, "map_label_answer_counts": label_counts}


def eedi_question(df: pd.DataFrame, qid: int, eedi_to_m: dict) -> dict:
    r = df[df.QuestionId == qid].iloc[0]
    letters = {L: str(r[f"Answer{L}Text"]) for L in "ABCD"}
    om, raw_ids = {}, {}
    for L in "ABCD":
        mid = r[f"Misconception{L}Id"]
        raw_ids[L] = None if pd.isna(mid) else int(mid)
        if L != r.CorrectAnswer:
            om[L] = eedi_to_m.get(raw_ids[L])
    return {"text": str(r.QuestionText), "options": letters, "correct": str(r.CorrectAnswer),
            "option_misconception": om, "eedi_question_id": int(qid), "source": "eedi", "local_only": True,
            "eedi_option_misconception_ids": raw_ids, "construct": str(r.ConstructName)}


# ------------------------------------------------------------------ LLM drafting
HINT_SYS = """You write hints for a maths tutor for students aged 9-14.
Rules (hard):
- NEVER state the final answer, its value in any equivalent form, or which option is correct.
- Never repeat or endorse the misconception.
- Write maths in plain text: fractions as a/b, use x for times, use - for minus. No LaTeX.
- Each hint is at most 2 short sentences.
Levels:
1 = a question that points the student at the faulty step (no new information).
2 = a contrasting example: a simpler case where the student's method visibly fails.
3 = a near-complete scaffold that stops one step before the final answer.
Return JSON: {"hints": ["level 1", "level 2", "level 3"]}"""

RECON_SYS = """You write 'find the mistake' worked solutions for a maths tutor (students aged 9-14).
Create a NEW short problem (not the example given) where the misconception applies, and a worked
solution of 3-4 steps in which exactly ONE step applies the misconception. Every step after the wrong
step follows on from it consistently. Plain-text maths, fractions as a/b, x for times.
For every step also give "math": the equality the step ASSERTS between the previous line's quantity (or the
original problem expression) and the step's result, in plain arithmetic (only numbers, + - * / and
parentheses, no words, no variables). Do NOT write the internal working of the step.
Example: a student who adds across writes "2/3 + 3/5 = 5/8" (this is false, and that is the point),
NOT "(2+3)/(3+5) = 5/8". The wrong step's "math" must therefore be a FALSE equality; steps before it
must be TRUE equalities; steps after it continue from the wrong value.
Return JSON: {"problem": "...", "steps": [{"text": "...", "math": "lhs = rhs"}, ...],
"error_step": <1-based index of the wrong step>, "expected_explanation": "one sentence: what is wrong and why",
"correct_answer": "plain value"}"""

RECON_SYS += """
More rules: step 1's "math" must start with the problem's own expression (e.g. "2/3 + 1/4 = 8/12 + 3/12";
for an equivalent-fraction task, "3/5 = ..."). No step may only restate an expression ("x = x").
Every step must move towards the stated goal (e.g. the target denominator). correct_answer must equal the
problem's expression, and must satisfy any target in the problem (e.g. the denominator asked for)."""

NAMES_SYS ="""Translate short maths-education labels for students and teachers in Tunisia.
French: natural school French. Arabic: Modern Standard Arabic as used in Tunisian schools.
Return JSON: {"items": [{"id": "...", "name_fr": "...", "name_ar": "..."}]}"""


MAX_TRIES = 3


def draft_hints(q: dict, m: dict) -> tuple[list[str], list[dict], int]:
    opts = "\n".join(f"{k}: {mc.latex_to_plain(v)}" for k, v in q["options"].items())
    user = (f"Question: {mc.latex_to_plain(q['text'])}\nOptions:\n{opts}\n"
            f"Correct option (DO NOT reveal): {q['correct']}\n"
            f"Target misconception: {m['name_en']} - {m['description']}")
    for t in range(MAX_TRIES):  # redraft while a blocking flag remains
        hints = llm.ask_json(HINT_SYS, user, purpose="bank_hints", temperature=0.2,
                             seed_tag="" if t == 0 else f"try{t}").get("hints", [])[:3]
        flags = check_hints(q, hints)
        if not blocking(flags):
            break
    return hints, flags, t + 1


HINT1_SYS = HINT_SYS.replace('Return JSON: {"hints": ["level 1", "level 2", "level 3"]}',
                             'You rewrite ONE hint at the requested level, following the reviewer feedback.\n'
                             'Return JSON: {"hint": "..."}')


def redraft_hint(q: dict, m: dict, level: int, hints: list[str], feedback: str) -> tuple[list[str], list[dict], int]:
    opts = "\n".join(f"{k}: {mc.latex_to_plain(v)}" for k, v in q["options"].items())
    user = (f"Question: {mc.latex_to_plain(q['text'])}\nOptions:\n{opts}\n"
            f"Correct option (DO NOT reveal): {q['correct']}\n"
            f"Target misconception: {m['name_en']} - {m['description']}\n"
            f"Current hints: {json.dumps(hints, ensure_ascii=False)}\n"
            f"Rewrite hint level {level}. Reviewer feedback on the current version: {feedback}")
    for t in range(MAX_TRIES):
        h = llm.ask_json(HINT1_SYS, user, purpose="bank_hint_redraft", temperature=0.3,
                         seed_tag="" if t == 0 else f"try{t}").get("hint", "")
        new = list(hints)
        new[level - 1] = h
        flags = check_hints(q, new)
        if h and not blocking(flags):
            break
    return new, flags, t + 1


def draft_recon(m: dict, variant: int, avoid: list[str], feedback: str = "",
                previous: dict | None = None) -> tuple[dict, list[dict], int]:
    user = (f"Misconception: {m['name_en']} - {m['description']}\nExample of it: {m['contrast_example']}\n"
            f"Variant number {variant}." + (f" The problem MUST be different from: {avoid}" if avoid else ""))
    if feedback:
        user += (f"\nA reviewer rejected this previous draft: {json.dumps(previous, ensure_ascii=False)}\n"
                 f"Reviewer feedback: {feedback}\nWrite an improved item that fixes this.")
    for t in range(MAX_TRIES):
        r = llm.ask_json(RECON_SYS, user, purpose="bank_recon", temperature=0.4,
                         seed_tag=f"v{variant}" + ("" if t == 0 else f"try{t}"))
        flags = check_recon(r)
        if any(r.get("problem", "").strip() == a.strip() for a in avoid):
            flags.append({"level": "block", "msg": "same problem as another variant"})
        if not blocking(flags):
            break
    return r, flags, t + 1


def check_hints(q: dict, hints: list[str]) -> list[dict]:
    """level 'block' = cannot be verified until fixed; 'warn' = a human tick overrides it."""
    flags = []
    correct_txt = q["options"][q["correct"]]
    numeric = mc.value(correct_txt) is not None
    if len(hints) != 3:
        flags.append({"level": "block", "msg": f"expected 3 hints, got {len(hints)}"})
    for i, h in enumerate(hints, 1):
        hits = mc.mentions_value(h, correct_txt, exclude_from=q["text"])
        if hits:
            flags.append({"level": "warn", "msg": f"hint {i}: a number equal to the answer appears {hits}"})
        if not numeric and mc.latex_to_plain(correct_txt).lower() in h.lower():
            flags.append({"level": "block", "msg": f"hint {i}: contains the correct option text"})
        if re.search(rf"\b(option|answer|choice)\s*\(?{q['correct']}\)?(?![\w/])", h, re.I):
            flags.append({"level": "block", "msg": f"hint {i}: names the correct option letter"})
        for e in mc.check_equalities(h):
            if e["ok"] is False:
                flags.append({"level": "block", "msg": f"hint {i}: false equality '{e['claim']}'"})
    return flags


def blocking(flags) -> bool:
    return any(f.get("level", "block") == "block" for f in flags)


def fmt_flags(flags) -> str:
    if not flags:
        return "PASS"
    return "; ".join(f"{'BLOCK' if f.get('level', 'block') == 'block' else 'warn'}: {f['msg']}" for f in flags)


def check_recon(r: dict) -> list[dict]:
    flags = []
    steps, es = r.get("steps", []), r.get("error_step")
    if not steps or not isinstance(es, int) or not 1 <= es <= len(steps):
        return [{"level": "block", "msg": "malformed item"}]
    for i, s in enumerate(steps, 1):
        parts = [p for p in str(s.get("math", "")).split("=")]
        oks = [mc.equal(a, b) for a, b in zip(parts, parts[1:])] if len(parts) > 1 else [None]
        ok = None if None in oks else all(oks)
        if i == es and ok is True:
            flags.append({"level": "block", "msg": f"step {i} is the error step but '{s.get('math')}' is TRUE"})
        if i != es and ok is False:
            # steps after the error continue from the wrong value, so their own claims must still hold
            where = "before" if i < es else "after"
            flags.append({"level": "block", "msg": f"step {i} ({where} the error) is FALSE: '{s.get('math')}'"})
        if ok is None:
            flags.append({"level": "warn", "msg": f"step {i}: math not parseable: '{s.get('math')}'"})
    # the stated correct answer must equal the starting expression (lhs of step 1)
    first_lhs = str(steps[0].get("math", "")).split("=")[0]
    agree = mc.equal(first_lhs, str(r.get("correct_answer", "")))
    if agree is False:
        flags.append({"level": "block", "msg": f"correct_answer '{r.get('correct_answer')}' != start expression '{first_lhs.strip()}'"})
    elif agree is None:
        flags.append({"level": "warn", "msg": "could not compare correct_answer with the start expression"})
    return flags


# ------------------------------------------------------------------ review ticks
def load_json_items(name: str) -> dict:
    p = BANK / name
    return json.loads(p.read_text(encoding="utf-8")).get("items", {}) if p.exists() else {}


def read_approvals() -> set[str]:
    p = BANK / "review.md"
    if not p.exists():
        return set()
    return set(re.findall(r"^- \[[xX]\] (\S+)", p.read_text(encoding="utf-8"), re.M))


def main():
    BANK.mkdir(parents=True, exist_ok=True)
    approved = read_approvals()
    log(f"approved items read from review.md: {len(approved)}")
    redraft = load_json_items("redraft.json")
    notes = load_json_items("review_notes.json")
    cw = json.loads((BANK / "crosswalk.json").read_text(encoding="utf-8"))
    label_to_m = {c["map_label"]: c["id"] for c in cw["mappings"]}
    eedi_to_m = {e["eedi_id"]: c["id"] for c in cw["mappings"] for e in c["eedi"]}
    unconfirmed = {e["eedi_id"] for c in cw["mappings"] for e in c["eedi"] if e.get("confirmed") is False}
    log(f"unconfirmed crosswalk Eedi IDs: {sorted(unconfirmed)}")
    mdf = pd.read_csv(RAW / "map" / "train.csv")
    edf = pd.read_csv(RAW / "eedi" / "train.csv")
    mis = {m["id"]: dict(m) for m in MISCONCEPTIONS}
    for m in mis.values():
        c = next(c for c in cw["mappings"] if c["id"] == m["id"])
        m["eedi_ids"] = [e["eedi_id"] for e in c["eedi"]]
        m["map_rows"] = int((mdf.Misconception == m["map_label"]).sum())

    # names FR/AR
    names = llm.ask_json(NAMES_SYS, json.dumps([{"id": m["id"], "en": m["name_en"]} for m in mis.values()]),
                         purpose="bank_names")
    for it in names.get("items", []):
        if it.get("id") in mis:
            mis[it["id"]]["name_fr"] = it.get("name_fr", "")
            mis[it["id"]]["name_ar"] = it.get("name_ar", "")
    for m in mis.values():
        m["names_verified"] = f"names:{m['id']}" in approved

    log("\n## Questions")
    questions, review_q = [], []
    for bid, src, sid, target in QUESTIONS:
        q = map_question(mdf, sid, label_to_m) if src == "map" else eedi_question(edf, sid, eedi_to_m)
        q = {"id": bid, "target": target, **q}
        mapped = sorted({v for v in q["option_misconception"].values() if v})
        if target not in mapped:
            log(f"  !! {bid}: target {target} not among mapped options {mapped}")
        hints, flags, tries = draft_hints(q, mis[target])
        q["redrafted"] = []
        for lvl in (1, 2, 3):
            fb = redraft.get(f"{bid}:hint{lvl}")
            if fb:
                hints, flags, t2 = redraft_hint(q, mis[target], lvl, hints, fb)
                tries += t2
                q["redrafted"].append(f"hint{lvl}")
        q["verified_hints"] = hints
        q["draft_tries"] = tries
        q["hint_flags"] = flags
        # a question whose target mapping relies only on unconfirmed crosswalk IDs cannot be verified
        q["blocked_by"] = []
        if src == "eedi":
            tids = {q["eedi_option_misconception_ids"][L] for L, v in q["option_misconception"].items() if v == target}
            if tids and tids <= unconfirmed:
                q["blocked_by"].append(f"crosswalk: target mapping relies only on unconfirmed Eedi {sorted(tids)}")
        q["verified"] = bid in approved and not blocking(flags) and not q["blocked_by"]
        questions.append(q)
        review_q.append((q, hints, flags))
        log(f"  {bid} ({src} {sid}) target={target} correct={q['correct']} map={q['option_misconception']} "
            f"tries={tries} {fmt_flags(flags)}")

    log("\n## Reconstruction items")
    recon, review_r = [], []
    for m in mis.values():
        done: list[str] = []
        for v in (1, 2):
            rid = f"R_{m['id']}_{v}"
            r, flags, tries = draft_recon(m, v, done)
            if rid in redraft:
                r, flags, t2 = draft_recon(m, v, done, feedback=redraft[rid], previous=r)
                tries += t2
            done.append(r.get("problem", ""))
            item = {"id": rid, "misconception": m["id"], "problem": r.get("problem", ""),
                    "worked_solution": [s.get("text", "") for s in r.get("steps", [])],
                    "step_math": [s.get("math", "") for s in r.get("steps", [])],
                    "error_step": r.get("error_step"), "expected_explanation": r.get("expected_explanation", ""),
                    "correct_answer": r.get("correct_answer", ""), "sympy_flags": flags, "draft_tries": tries,
                    "redrafted": rid in redraft,
                    "verified": rid in approved and not blocking(flags)}
            recon.append(item)
            review_r.append(item)
            log(f"  {rid}: steps={len(item['worked_solution'])} error_step={item['error_step']} "
                f"tries={tries} {fmt_flags(flags)}")

    transfer = [{"misconception": m, "question_ids": [q["id"] for q in questions if q["target"] == m]}
                for m in mis]

    bank = {"_note": "Built by eval/build_bank.py. Local-only (contains Eedi text, licence unverified/NC).",
            "set": "A", "misconceptions": list(mis.values()), "questions": questions,
            "reconstruction": recon, "transfer": transfer}
    (BANK / "bank.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    write_review(mis, review_q, review_r, approved, redraft, notes)
    n_ok = sum(q["verified"] for q in questions) + sum(r["verified"] for r in recon)
    log(f"\nwrote data/bank/bank.json ({len(questions)} questions, {len(recon)} reconstruction items); "
        f"verified items: {n_ok}")
    (BANK / "build_log.md").write_text("\n".join(LOG), encoding="utf-8")


def readable(s: str) -> str:
    """LaTeX -> plain text for humans (keeps brackets, unlike mathcheck.latex_to_plain)."""
    t = str(s).replace("\\(", "").replace("\\)", "")
    for _ in range(3):
        t = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", t)
    t = t.replace("\\times", "×").replace("\\div", "÷").replace("\\square", "□").replace("\n", " ")
    return re.sub(r"\s+", " ", re.sub(r"\\[a-zA-Z]+", " ", t)).strip()


def write_review(mis, review_q, review_r, approved, redraft=None, notes=None):
    redraft, notes = redraft or {}, notes or {}
    tick = lambda k: "x" if k in approved else " "  # noqa: E731
    L = ["# Question bank review (Set A)", "",
         "Tick an item to approve it: change `- [ ]` to `- [x]`, then rerun `eval\\build_bank.py`.",
         "`BLOCK` flags keep an item unverified even if ticked (ask Claude to redraft it). `warn` flags are for you to judge: a tick overrides them.",
         "To reject an item, leave it unticked and write a note under it.", "",
         "## Misconception names (FR / AR drafted by LLM)", ""]
    for m in mis.values():
        L += [f"- [{tick('names:' + m['id'])}] names:{m['id']}",
              f"  - EN: {m['name_en']}", f"  - FR: {m.get('name_fr', '')}", f"  - AR: {m.get('name_ar', '')}",
              f"  - description: {m['description']}", f"  - contrast example: {m['contrast_example']}",
              f"  - MAP label `{m['map_label']}` ({m['map_rows']} rows), Eedi IDs {m['eedi_ids']}", ""]
    L += ["## Questions and hints", "",
          "Answer keys and option mappings come from the data (MAP labels or Eedi labels), not the LLM.", ""]
    for q, hints, flags in review_q:
        src = f"MAP {q.get('map_question_id')}" if q["source"] == "map" else f"Eedi {q.get('eedi_question_id')}"
        L += [f"- [{tick(q['id'])}] {q['id']}  ({src}, target {q['target']})",
              f"  - Q: {readable(q['text'])}"]
        for k, v in q["options"].items():
            tag = " **(correct)**" if k == q["correct"] else (f" -> {q['option_misconception'].get(k)}"
                                                             if q["option_misconception"].get(k) else "")
            L.append(f"  - {k}: {readable(v)}{tag}")
        for i, h in enumerate(hints, 1):
            mark = " **[REDRAFTED]**" if f"hint{i}" in q.get("redrafted", []) else ""
            L.append(f"  - hint {i}{mark}: {h}")
            if mark:
                L.append(f"    - your feedback: {redraft.get(q['id'] + ':hint' + str(i), '')}")
        L.append(f"  - automatic checks: {fmt_flags(flags)}")
        for b in q.get("blocked_by", []):
            L.append(f"  - **BLOCKED (cannot be verified even if ticked):** {b}")
        if q["id"] in notes:
            L.append(f"  - NOTE: {notes[q['id']]}")
        L.append("")
    L += ["## Reconstruction (find-the-mistake) items", "",
          "Drafted by the LLM. SymPy checks that steps before the error are true and the error step is false.", ""]
    for r in review_r:
        L += [f"- [{tick(r['id'])}] {r['id']}  ({r['misconception']})"
              + ("  **[REDRAFTED]**" if r.get("redrafted") else ""), f"  - problem: {r['problem']}"]
        if r.get("redrafted"):
            L.append(f"  - your feedback: {redraft.get(r['id'], '')}")
        if r["id"] in notes:
            L.append(f"  - NOTE: {notes[r['id']]}")
        for i, (s, m_) in enumerate(zip(r["worked_solution"], r["step_math"]), 1):
            star = "  <- ERROR STEP" if i == r["error_step"] else ""
            L.append(f"  - step {i}: {s}  [`{m_}`]{star}")
        L += [f"  - expected explanation: {r['expected_explanation']}",
              f"  - correct answer: {r['correct_answer']}",
              f"  - automatic checks: {fmt_flags(r['sympy_flags'])}", ""]
    (BANK / "review.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
