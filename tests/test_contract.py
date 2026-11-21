"""Contract + frontend-rule enforcement (docs/INTERFACE.md section 1)."""
import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine import ROOT, api, api_fake, safetext
from engine.contract import (Check, NextQuestion, SafeText, SessionState, SessionSummary, StudioOutput,
                             TutorTurn)

FX = ROOT / "docs" / "fixtures"
FRONTEND = [ROOT / "app.py", *sorted((ROOT / "pages").glob("*.py")), *sorted((ROOT / "ui").glob("*.py"))]
HAS_BANK = (ROOT / "data" / "bank" / "bank.json").exists()

MODELS = {"session_state": SessionState, "tutor_turn": TutorTurn, "tutor_turn_reconstruct": TutorTurn,
          "next_question": NextQuestion, "session_summary": SessionSummary, "studio_output": StudioOutput,
          "studio_output_refused": StudioOutput}


# ---------------------------------------------------------------- shapes
@pytest.mark.parametrize("name", MODELS)
def test_fixtures_validate(name):
    MODELS[name].model_validate(json.loads((FX / f"{name}.json").read_text(encoding="utf-8")))


def test_fake_api_matches_contract():
    s = api_fake.start_session({"name": "X"})
    SessionState.model_validate(s)
    TutorTurn.model_validate(api_fake.submit_answer(s["session_id"], "Q1", "A", "sure"))
    TutorTurn.model_validate(api_fake.tutor_reply(s["session_id"], text="step 2"))
    SessionSummary.model_validate(api_fake.summary(s["session_id"]))
    StudioOutput.model_validate(api_fake.studio_generate(s["session_id"], "slides", {"kind": "diagnosis"}))
    r = api_fake.studio_generate(s["session_id"], "summary", {"folder_allow_derivatives": False})
    assert r["refused"] and not r["items"]


@pytest.mark.skipif(not HAS_BANK, reason="bank.json is local-only")
def test_real_api_matches_contract_and_hides_keys():
    s = api.start_session({"name": "X", "level": "7e", "lang": "fr"})
    SessionState.model_validate(s)
    json.dumps(s)  # JSON-serialisable
    q = s["current_question"]
    assert set(q) == {"id", "text", "options", "requires_confidence", "why_mode", "why_options"}
    with pytest.raises(ValueError):
        api.submit_answer(s["session_id"], q["id"], "A", None)  # confidence tap required
    t = api.submit_answer(s["session_id"], q["id"], "A", "sure")
    TutorTurn.model_validate(t)
    assert t["grading"]["method"] == "answer_key"
    assert abs(sum(h["prob"] for h in t["posterior"]) - 1) < 1e-4
    NextQuestion.model_validate(api.next_question(s["session_id"]))


# ---------------------------------------------------------------- SafeText rule
def test_safetext_shown_only_when_all_checks_pass():
    ok = [Check(name=n, status="pass") for n in ("leak", "congruency", "math", "style")]
    assert safetext.from_guards("Look at the denominators.", ok).shown_allowed
    bad = ok[:3] + [Check(name="style", status="fail")]
    assert not safetext.from_guards("x", bad).shown_allowed
    assert not safetext.from_guards("x", ok[:3]).shown_allowed  # style never ran -> not allowed
    with pytest.raises(ValidationError):
        SafeText(text="x", origin="llm", checks=ok[:3], shown_allowed=True)


def test_static_text_runs_style_linter():
    assert safetext.static("Your answer is saved.").shown_allowed
    assert not safetext.static("Great job!").shown_allowed  # '!' in neutral mode


# ---------------------------------------------------------------- frontend rules (static analysis)
FORBIDDEN_MODULES = {"numpy", "scipy", "groq", "openai", "anthropic", "requests", "httpx", "sklearn", "sympy"}
ALLOWED_ENGINE = {"engine.api", "engine.api_fake"}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "engine":
                for a in node.names:
                    yield f"engine.{a.name}"
            else:
                yield mod


@pytest.mark.parametrize("path", FRONTEND, ids=lambda p: p.name)
def test_frontend_imports(path):
    for mod in _imports(path):
        top = mod.split(".")[0]
        assert top not in FORBIDDEN_MODULES, f"{path.name} imports {mod} (no diagnosis math / no direct LLM)"
        if top == "engine":
            assert mod in ALLOWED_ENGINE, f"{path.name} imports {mod}; only engine.api / engine.api_fake allowed"


@pytest.mark.parametrize("path", FRONTEND, ids=lambda p: p.name)
def test_frontend_never_writes_files(path):
    src = path.read_text(encoding="utf-8")
    for bad in ("write_text(", "json.dump(", "to_json(", "to_csv(", '"w")', "'w')", '"a")', "'a')"):
        assert bad not in src, f"{path.name} writes files ({bad}); results/*.json are read-only"


def test_read_results_is_a_copy_and_safe():
    names = api.list_results()
    if names:
        a = api.read_results(names[0])
        a["tampered"] = True
        assert "tampered" not in api.read_results(names[0])
    with pytest.raises(ValueError):
        api.read_results("../config")
