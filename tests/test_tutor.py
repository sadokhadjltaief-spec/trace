"""Tutor state machine + guards, with the LLM replaced by canned answers (no network)."""
import pytest

from engine import ROOT, api, guards, llm
from engine.contract import SessionState, TutorTurn

HAS_BANK = (ROOT / "data" / "bank" / "bank.json").exists()
Q1 = {"id": "Q1", "text": r"\( \frac{1}{3}+\frac{2}{5}= \)", "correct": "D",
      "options": {"A": r"\( \frac{3}{15} \)", "B": r"\( \frac{11}{30} \)", "C": r"\( \frac{3}{8} \)",
                  "D": r"\( \frac{11}{15} \)"}}
NAMES = {"M0": "none", "M1": "Adds numerators and adds denominators", "M2": "x", "M3": "y", "M4": "z"}


def test_deterministic_leak():
    assert guards.deterministic_leak("The answer is option D.", Q1)
    assert guards.deterministic_leak("So you get 11/15.", Q1)
    assert guards.deterministic_leak("That makes 22/30.", Q1)          # same value as the answer
    assert not guards.deterministic_leak("What does the 3 in 1/3 tell you?", Q1)


def test_math_check():
    assert guards.math_check("Note that 1/2 + 1/2 = 2/4.")[0] == "fail"
    assert guards.math_check("Note that 1/2 + 1/4 = 3/4.")[0] == "pass"


def _judge(reveals=False, congruent=None):
    def f(system, user, **kw):
        assert kw["purpose"] == "guard_judge"
        return {"reveals_answer": reveals, "leak_reason": "r", "congruent": congruent or {}, "congruency_reason": "c"}
    return f


def test_check_all_pass_and_fail_closed(monkeypatch):
    post = {"M0": 0.1, "M1": 0.8, "M2": 0.05, "M3": 0.03, "M4": 0.02}
    monkeypatch.setattr(llm, "ask_json", _judge())
    checks, _ = guards.check("Look at the bottom numbers. What do they tell you?", Q1, post, NAMES)
    assert {c.name: c.status for c in checks} == {"style": "pass", "math": "pass", "leak": "pass", "congruency": "pass"}
    monkeypatch.setattr(llm, "ask_json", _judge(congruent={"M1": True}))
    checks, _ = guards.check("Add the tops and the bottoms.", Q1, post, NAMES)
    assert {c.name: c.status for c in checks}["congruency"] == "fail"

    def boom(*a, **k):
        raise llm.CacheMiss("demo")
    monkeypatch.setattr(llm, "ask_json", boom)
    checks, _ = guards.check("Look at the bottom numbers.", Q1, post, NAMES)
    assert {c.name: c.status for c in checks}["leak"] == "fail"   # judge unavailable -> fail closed


def _fake_llm(hint_text):
    def f(system, user, *, purpose, **kw):
        if purpose == "guard_judge":
            return {"reveals_answer": False, "congruent": {}, "leak_reason": "", "congruency_reason": ""}
        if purpose == "tutor_diagnosis":
            return {"error": "added across", "faulty_step": "adding denominators", "correct_idea": "same size parts"}
        if purpose.startswith("tutor_hint"):
            return {"message": hint_text(purpose, kw.get("seed_tag", ""))}
        if purpose == "tutor_recon_rubric":
            return {"verdict": "correct", "reason": "names the error"}
        if purpose.startswith("detector"):
            raise llm.LLMError("not in this test")
        raise AssertionError(purpose)
    return f


def _diagnose_as(sid, h):
    s = api.get_state(sid)
    for _ in range(10):
        q = s["current_question"]
        bq = api._SESSIONS[sid]["by_id"][q["id"]]
        opt = next((o for o, m in bq.get("option_misconception", {}).items() if m == h),
                   next(o for o in bq["options"] if o != bq["correct"]))
        t = api.submit_answer(sid, q["id"], opt, "sure")
        TutorTurn.model_validate(t)
        if t["state"] != "DIAGNOSE":
            return t
        s = api.get_state(sid)
    raise AssertionError("diagnosis did not stop")


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_hint_flow_to_reconstruct(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", _fake_llm(lambda p, tag: "Look at the bottom numbers. What size are the parts?"))
    sid = api.start_session({"name": "T", "lang": "en"}, detector_llm=False)["session_id"]
    t = _diagnose_as(sid, "M1")
    assert t["state"] == "HINT_1" and t["expects"] == "retry"
    assert t["message"]["origin"] == "llm" and t["message"]["shown_allowed"]
    rq = api._SESSIONS[sid]["by_id"][t["question"]["id"]]
    assert set(t["question"]) == {"id", "text", "options", "requires_confidence", "why_mode", "why_options"}
    wrong = next(o for o in rq["options"] if o != rq["correct"])
    t2 = api.tutor_reply(sid, choice=wrong)
    assert t2["state"] == "HINT_2" and t2["grading"]["correct"] is False
    t3 = api.tutor_reply(sid, choice=rq["correct"])
    assert t3["state"] == "RECONSTRUCT" and t3["expects"] == "error_step"
    assert "error_step" not in t3["reconstruction"]
    SessionState.model_validate(api.get_state(sid))
    with pytest.raises(ValueError):
        api.submit_answer(sid, rq["id"], "A", "sure")  # diagnosis is over


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_leaking_hint_regenerates_then_falls_back(monkeypatch):
    seen = []

    def leaky(purpose, tag):
        seen.append(tag)
        return "Well done! Look at the bottom numbers."  # "!" fails the style linter (neutral mode)
    monkeypatch.setattr(llm, "ask_json", _fake_llm(leaky))
    sid = api.start_session({"name": "T", "lang": "en"}, detector_llm=False)["session_id"]
    t = _diagnose_as(sid, "M1")
    assert t["state"] == "HINT_1"
    assert seen == ["", "regen1"]                          # one regeneration, then fallback
    assert t["message"]["fallback_used"] and t["message"]["origin"] in ("verified_bank", "template")
    assert t["message"]["shown_allowed"]
    assert any(e["status"] == "fail" and e["action"] == "fallback" for e in t["guard_events"])


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_demo_cache_miss_falls_back(monkeypatch):
    def miss(*a, **k):
        raise llm.CacheMiss("not cached")
    monkeypatch.setattr(llm, "ask_json", miss)
    sid = api.start_session({"name": "T", "lang": "en"}, detector_llm=False)["session_id"]
    t = _diagnose_as(sid, "M1")
    assert t["state"] == "HINT_1" and t["message"]["fallback_used"] and t["message"]["shown_allowed"]


@pytest.mark.parametrize("text,lang,ok", [
    ("Regarde les dénominateurs. Que représentent-ils ?", "fr", True),
    ("Look at the bottom numbers. What do they tell you?", "fr", False),
    ("انظر إلى المقامات. ماذا يعني العدد 3 في 1/3؟", "ar", True),
    ("Regarde les dénominateurs.", "ar", False),
    ("Look at the bottom numbers.", "en", True),
])
def test_language_check(text, lang, ok):
    assert (guards.language_check(text, lang) is None) == ok


def test_wrong_language_fails_style(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", _judge())
    post = {"M0": 0.1, "M1": 0.8, "M2": 0.05, "M3": 0.03, "M4": 0.02}
    checks, _ = guards.check("Look at the bottom numbers.", Q1, post, NAMES, lang="fr")
    assert {c.name: c.status for c in checks}["style"] == "fail"


def test_recon_giveaway_neutralised():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_bank", ROOT / "eval" / "build_bank.py")
    bb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bb)
    steps, changed = bb.neutralise_steps(["Add by (incorrectly) adding tops: 8/12 + 3/12 = 11/24.",
                                          "(Incorrect) Multiply the denominator by 4 as well.", "Write 3/4."])
    assert steps == ["Add by adding tops: 8/12 + 3/12 = 11/24.", "Multiply the denominator by 4 as well.", "Write 3/4."]
    assert changed == [1, 2]
    assert bb.GIVEAWAY_WORD.search("this step is wrong") and not bb.GIVEAWAY_WORD.search("Write the result")


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_fallback_stays_in_student_language(monkeypatch, lang):
    def miss(*a, **k):
        raise llm.CacheMiss("not cached")
    monkeypatch.setattr(llm, "ask_json", miss)
    sid = api.start_session({"name": "T", "lang": lang}, detector_llm=False)["session_id"]
    t = _diagnose_as(sid, "M1")
    assert t["message"]["fallback_used"] and t["message"]["lang"] == lang and t["message"]["shown_allowed"]
    assert guards.language_check(t["message"]["text"], lang) is None


def _to_reconstruct(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", _fake_llm(lambda p, tag: "Look at the bottom numbers. What size are the parts?"))
    sid = api.start_session({"name": "T", "lang": "en"}, detector_llm=False)["session_id"]
    t = _diagnose_as(sid, "M1")
    rq = api._SESSIONS[sid]["by_id"][t["question"]["id"]]
    t = api.tutor_reply(sid, choice=rq["correct"])
    assert t["state"] == "RECONSTRUCT"
    return sid, t


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_full_path_to_mastered(monkeypatch):
    from engine import tutor
    sid, t = _to_reconstruct(monkeypatch)
    s = api._SESSIONS[sid]
    t = api.tutor_reply(sid, choice=str(s["recon"]["error_step"]), text="they added the bottoms")
    assert t["grading"]["method"] == "llm_rubric" and "LLM" in t["grading"]["label"]
    assert t["state"] == "TRANSFER" and t["expects"] == "transfer_answer"
    tq = s["by_id"][t["question"]["id"]]
    assert tq["target"] == "M1" and tq["id"] not in {a.question_id for a in s["asked"]}
    n_before = len(s["diag"].history)
    t = api.tutor_reply(sid, choice=tq["correct"])
    assert t["state"] == "DONE" and t["grading"]["method"] == "answer_key"
    assert len(s["diag"].history) == n_before + 1          # transfer answer is Bayes evidence
    assert tutor.mastery_status(s) == "mastered"
    with pytest.raises(ValueError):
        api.tutor_reply(sid, choice="A")


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_reconstruct_wrong_twice_then_transfer(monkeypatch):
    sid, t = _to_reconstruct(monkeypatch)
    s = api._SESSIONS[sid]
    wrong = 1 if s["recon"]["error_step"] != 1 else 2
    t = api.tutor_reply(sid, choice=str(wrong))
    assert t["state"] == "RECONSTRUCT" and t["grading"]["correct"] is False
    t = api.tutor_reply(sid, choice=str(wrong))
    assert t["state"] == "TRANSFER" and f"step {s['recon']['error_step']}" in t["message"]["text"]


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_transfer_fails_loops_then_handoff(monkeypatch):
    sid, t = _to_reconstruct(monkeypatch)
    s = api._SESSIONS[sid]
    states = []
    for _ in range(12):
        if t["state"] == "RECONSTRUCT":
            t = api.tutor_reply(sid, choice=str(s["recon"]["error_step"]), text="x")
        elif t["state"] == "TRANSFER":
            q = s["by_id"][t["question"]["id"]]
            t = api.tutor_reply(sid, choice=next(o for o in q["options"] if o != q["correct"]))
        elif t["state"].startswith("HINT"):
            q = s["by_id"][t["question"]["id"]]
            t = api.tutor_reply(sid, choice=q["correct"])
        else:
            break
        states.append(t["state"])
    assert t["state"] == "HANDOFF"
    assert 1 <= states.count("HINT_1") <= 2
    assert len(s["handoff_note"].splitlines()) == 3
    tq = [x["question_id"] for x in s["outcome"]["transfers"]]
    assert all(s["by_id"][q]["target"] == "M1" for q in tq)   # transfer = same misconception only
    TutorTurn.model_validate(t)
