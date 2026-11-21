"""Step 10 (support profiles + style linter) and FR/AR templates."""
import collections
import json
import re

import pytest

from engine import ROOT, api, guards, llm, style

HAS_BANK = (ROOT / "data" / "bank" / "bank.json").exists()


def test_profiles_and_preset():
    d = style.defaults()
    assert not any(v for k, v in d.items() if k not in ("max_words_per_sentence", "example_theme"))
    p = style.resolve({"preset": "clear_structured"})
    assert p["literal_language"] and p["fixed_template"] and p["structured_why"] and p["max_words_per_sentence"] == 15
    assert not p["calm_theme"]                                       # preset = toggles 1-6 only
    assert style.resolve({"preset": "clear_structured", "fixed_template": False})["fixed_template"] is False
    assert style.prompt_rules({}) == ""                               # default prompts unchanged (cache stays valid)
    assert "ONE question" in style.prompt_rules({"preset": "clear_structured"})


@pytest.mark.parametrize("text,lang,kw,bad", [
    ("This is a piece of cake.", "en", {"literal": True}, "idiom"),
    ("C'est du gâteau.", "fr", {"literal": True}, "idiom"),
    ("هذا سهل كشرب الماء.", "ar", {"literal": True}, "idiom"),
    ("Great job. Now look at step 2.", "en", {"no_praise": True}, "praise"),
    ("Bravo. Regarde l'étape 2.", "fr", {"no_praise": True}, "praise"),
    ("أحسنت. انظر إلى الخطوة 2.", "ar", {"no_praise": True}, "praise"),
    ("Is it bigger? Is it smaller?", "en", {"max_questions": 1}, "question mark"),
    ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen.", "en",
     {"max_words_per_sentence": 15}, "words"),
])
def test_lint_catches(text, lang, kw, bad):
    v = style.lint(text, lang=lang, **kw)
    assert any(bad in x for x in v), v


def test_lint_no_false_positive():
    assert style.lint("La valeur est supérieure à 1/2.", lang="fr", no_praise=True, literal=True) == []
    assert style.lint("Look at the bottom numbers.", lang="en", no_praise=True, literal=True, max_questions=1) == []


def test_i18n_complete():
    tab = json.loads((ROOT / "i18n" / "tutor.json").read_text(encoding="utf-8"))
    for k, row in tab.items():
        if k.startswith("_"):
            continue
        assert set(row) == {"en", "fr", "ar"} and all(row.values()), k
        assert guards.language_check(row["ar"], "ar") is None, k
        for lg in ("en", "fr", "ar"):  # every fixed string passes the clear-mode linter
            assert style.lint(row[lg].format_map(collections.defaultdict(lambda: "2")), lang=lg, max_words_per_sentence=15, max_questions=1,
                              literal=True, no_praise=True) == [], (k, lg)


def _fake(system, user, *, purpose, **kw):
    if purpose == "guard_judge":
        return {"reveals_answer": False, "congruent": {}, "claims": []}
    if purpose == "tutor_diagnosis":
        return {"error": "e", "faulty_step": "s", "correct_idea": "i"}
    if purpose.startswith("tutor_hint"):
        lang = "ar" if "Arabic" in system else "fr" if "French" in system else "en"
        return {"message": {"fr": "Regarde les dénominateurs. Que représentent-ils ?",
                            "ar": "انظر إلى المقامات. ماذا تعني؟",
                            "en": "Look at the bottom numbers. What do they mean?"}[lang]}
    if purpose == "tutor_recon_rubric":
        return {"verdict": "correct", "reason": "r"}
    raise llm.LLMError("no LLM here")


def _run(lang, profile=None):
    sid = api.start_session({"name": "T", "lang": lang}, profile=profile, detector_llm=False)["session_id"]
    s = api._SESSIONS[sid]
    turns = []
    for _ in range(10):
        q = api.get_state(sid)["current_question"]
        bq = s["by_id"][q["id"]]
        opt = next((o for o, m in bq.get("option_misconception", {}).items() if m == "M1"),
                   next(o for o in bq["options"] if o != bq["correct"]))
        t = api.submit_answer(sid, q["id"], opt, "sure")
        turns.append(t)
        if t["state"] != "DIAGNOSE":
            break
    t = api.tutor_reply(sid, choice=s["by_id"][t["question"]["id"]]["correct"])
    turns.append(t)
    t = api.tutor_reply(sid, choice=str(s["recon"]["error_step"]), text="x")
    turns.append(t)
    turns.append(api.tutor_reply(sid, choice=s["by_id"][t["question"]["id"]]["correct"]))
    return sid, turns


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_every_message_in_student_language(monkeypatch, lang):
    monkeypatch.setattr(llm, "ask_json", _fake)
    sid, turns = _run(lang)
    assert turns[-1]["state"] == "DONE"
    for t in turns:
        m = t["message"]
        assert m["shown_allowed"] and m["lang"] == lang, (t["state"], m["text"])
        assert guards.language_check(m["text"], lang) is None, (t["state"], m["text"])
        assert guards.language_check(t["agenda"]["next"], lang) is None if lang == "ar" else True
    r = api.summary(sid)
    assert r["outcome"]["lang"] == lang and guards.language_check(r["outcome"]["text"], lang) is None


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_clear_structured_mode(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", _fake)
    sid, turns = _run("fr", profile={"preset": "clear_structured"})
    st = api.get_state(sid)
    assert st["profile"]["fixed_template"] and st["profile"]["structured_why"]
    for t in turns:
        m = t["message"]
        assert m["shown_allowed"], m
        lines = m["text"].split("\n")
        assert lines[0].startswith("Situation: ") and lines[1].startswith("Ta tâche: ")
        assert lines[2].startswith("Ensuite: ")
        assert m["text"].count("?") <= 1
    q = api.get_state(sid)
    s2 = api.start_session({"name": "T", "lang": "fr"}, profile={"preset": "clear_structured"})
    why = s2["current_question"]["why_options"]
    assert s2["current_question"]["why_mode"] == "structured" and why[0]["lang"] == "fr"


HAS_TR = (ROOT / "data" / "bank" / "bank_i18n.json").exists()


@pytest.mark.skipif(not (HAS_BANK and HAS_TR), reason="bank files are local-only")
def test_bank_translations_keep_the_maths():
    from engine import i18n, mathcheck as mc
    bank = json.loads((ROOT / "data" / "bank" / "bank.json").read_text(encoding="utf-8"))
    for q in bank["questions"]:
        for lang in ("fr", "ar"):
            text, opts = i18n.question(q, lang)
            assert sorted(mc.numeric_tokens(text)) == sorted(mc.numeric_tokens(q["text"])), (q["id"], lang)
            assert set(opts) == set(q["options"])
            for k in opts:
                assert mc.numeric_tokens(opts[k]) == mc.numeric_tokens(q["options"][k]), (q["id"], k)
            def strip(s):  # text outside the LaTeX \( ... \) blocks
                return re.sub(r"\\\(.*?\\\)", " ", s, flags=re.S)
            if lang == "ar":
                assert not re.search(r"[A-Za-z]{2,}", strip(text)), (q["id"], strip(text))
            elif re.search(r"[A-Za-z]{3,}", strip(q["text"])):
                assert strip(text) != strip(q["text"]), q["id"]  # FR stem translated
    for r in bank["reconstruction"]:
        for lang in ("fr", "ar"):
            problem, steps = i18n.reconstruction(r, lang)
            assert len(steps) == len(r["worked_solution"]), r["id"]
            assert sorted(mc.numeric_tokens(problem)) == sorted(mc.numeric_tokens(r["problem"])), (r["id"], lang)
            for a, b in zip(steps, r["worked_solution"]):
                assert sorted(mc.numeric_tokens(a)) == sorted(mc.numeric_tokens(b)), (r["id"], lang, a)
