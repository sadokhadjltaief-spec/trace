# TRACE frontend ↔ engine interface (contract v1.0)

This is the contract between the engine (built by Claude Code) and the frontend pages (built by the teammate).
The source of truth is **`engine/contract.py`** (pydantic models). This file explains it.
JSON Schemas: `docs/schema/*.json`. Fake examples: `docs/fixtures/*.json` (regenerate with
`.\.venv\Scripts\python.exe scripts\make_fixtures.py`).
Any change to a field bumps `CONTRACT_VERSION` and updates this file, the schemas and the fixtures in the same commit.

## 1. Rules (enforced by `tests/test_contract.py`)

1. **The frontend imports only `engine.api` (real) or `engine.api_fake` (fake fixtures) from the engine.**
   No `engine.bayes`, `engine.llm`, `engine.guards`, `engine.detector`, … in `app.py` or `pages/`.
2. **No diagnosis math in the frontend.** Probabilities, information gain, entropy, grading and stop decisions all
   arrive ready-made in the objects below. The frontend displays them; it never computes, re-normalises or
   re-ranks them, and it does not import numpy/scipy for that purpose (the test forbids numpy/scipy imports in pages).
3. **No direct LLM calls from the frontend.** No `groq`, `openai`, `anthropic`, `requests`/`httpx` to model APIs.
   Every LLM call goes through `engine/llm.py`, which the engine calls for you.
4. **Guards and the style linter run before any text is displayed.** Every displayable text is a `SafeText`.
   Render it **only if `shown_allowed` is true**. The engine sets `shown_allowed = true` only when all four
   checks (`leak`, `congruency`, `math`, `style`) ran and none failed (the model validator enforces this).
   Use the helper `ui.show_text()`; it refuses to render a `SafeText` that is not allowed.
   Question text and option text in `QuestionView` come from the reviewed bank and are shown as they are.
5. **`results/*.json` are read-only for the frontend.** Read them with `api.read_results(name)` (returns a copy).
   Never write to `results/`, never hard-code a metric; show each number next to the script that produced it
   (`"script"` field in each results file).
6. The frontend never sees answer keys, option→misconception maps or the error step of a worked solution:
   these stay in the engine (`QuestionView` and `Reconstruction` do not have those fields).
7. Clear and structured mode: when `profile` has clear-mode toggles on, the student view hides animated
   probability bars (teacher/judge view only), shows `agenda`, and uses `why_mode == "structured"`.
8. Every Study Studio output with `targeted_at` must show the line **`Targeted at: <name>`**, and list `sources`.
   If `refused` is set, show the refusal text and nothing else.

## 2. Functions the frontend calls (`engine/api.py`, same names in `engine/api_fake.py`)

| function | returns | status |
|---|---|---|
| `start_session(student, profile=None, demo=False)` | `SessionState` | real |
| `get_state(session_id)` | `SessionState` | real |
| `next_question(session_id)` | `NextQuestion` | real |
| `submit_answer(session_id, question_id, option, confidence, explanation=None)` | `TutorTurn` | real (diagnosis phase) |
| `tutor_reply(session_id, text=None, choice=None)` | `TutorTurn` | fake until step 6–8 |
| `summary(session_id)` | `SessionSummary` | fake until step 9 |
| `studio_generate(session_id, tool, source)` | `StudioOutput` | fake until step 12 |
| `misconceptions()` | `list[MisconceptionView]` | real |
| `list_results()` / `read_results(name)` | `list[str]` / `dict` (read-only copy) | real |

`student = {"name": str, "level": str, "lang": "fr"|"ar"|"en"}`.
`confidence` is required: `"sure"` or `"unsure"` (the UI must block submit until it is chosen).
`source` for Study Studio: `{"kind": "diagnosis"|"folder"|"pages", "folder": str?, "pages": [...]?}`.
All functions return plain dicts (`model.model_dump()`), JSON-serialisable.

## 3. Shapes

### SafeText (every displayable text)
```json
{"text": "…", "lang": "fr|ar|en", "origin": "llm|verified_bank|template",
 "checks": [{"name": "leak|congruency|math|style", "status": "pass|fail|not_applicable", "detail": "…"}],
 "shown_allowed": true, "fallback_used": false}
```
`template`/`verified_bank` text: leak/congruency/math are `not_applicable`, the style linter always runs.
`llm` text: all four checks must be `pass`.

### SessionState: `docs/fixtures/session_state.json`
`session_id, student, profile, demo_mode, state` (DIAGNOSE … HANDOFF), `agenda {step,total,next}`,
`posterior [{id,name_en,prob}]` (M0..M4, sums to 1), `top`, `asked [AnswerRecord]`,
`current_question QuestionView|null`, `next_question NextQuestion`, `fragile [question_id]`,
`guard_events [GuardEvent]`, `cost Cost`, `warnings [str]` (show them, e.g. dev-mode bank warning).

### QuestionView
`{id, text, options {letter: text}, requires_confidence, why_mode "free"|"structured", why_options [SafeText]}`.
Text may contain LaTeX `\( … \)`; convert to `$…$` for `st.markdown`.

### NextQuestion: `docs/fixtures/next_question.json`
`{question_id|null, ig_bits, alternatives [{question_id, ig_bits}], entropy_bits, stop, stop_reason}`.
Judge panel text: "Next question chosen because IG = {ig_bits} bits (alternatives …)".

### TutorTurn: `docs/fixtures/tutor_turn.json`, `tutor_turn_reconstruct.json`
`{turn_id, state, message SafeText, expects "answer|retry|error_step|explanation|transfer_answer|none",
agenda, question QuestionView|null, reconstruction {id, problem, steps[]}|null,
grading {correct|null, method "answer_key|sympy|simulation|llm_rubric|none", label}, posterior, next_question|null,
guard_events}`. Show `grading.label`; `llm_rubric` must be visibly labelled as LLM-graded.

### SessionSummary: `docs/fixtures/session_summary.json`
`{diagnosis HypProb, diagnosis_names {id,name_en,name_fr,name_ar}, status "mastered|in_progress|handoff|no_misconception",
evidence [str], tried [state], outcome SafeText, next_step SafeText, lesson_refs [{file,page,snippet,source_url}],
handoff_note SafeText|null, calibration {sure_correct,sure_total,unsure_correct,unsure_total}, cost}`.

### StudioOutput: `docs/fixtures/studio_output.json`, `studio_output_refused.json`
`{tool, targeted_at MisconceptionView|null, sources [{file,page,timestamp}], files [{path,mime}], items [...], refused str|null}`.
`items` is tool-specific; every text inside an item is a SafeText dict. Flashcards: `{front, back, verified, misconception}`.

### GuardEvent, Cost
`GuardEvent {ts, check, status "pass|fail", action "shown|regenerated|fallback", summary}`.
`Cost {calls, cached_calls, prompt_tokens, completion_tokens, label}`. Cached replays count as calls but not tokens.
Label is "free tier, rate-limited"; no prices are shown (none configured).

## 4. Stub pages
`app.py` and `pages/` are **stubs** that show every shape working, with a sidebar switch
"Data: engine / fake fixtures". The teammate replaces them, keeping this contract and the rules above.
`ui/__init__.py` holds the display helpers (`show_text`, `latex_to_md`, `backend`) that enforce rule 4.
The frontend is `app.py`, `pages/` and `ui/`; the rules in section 1 apply to all three.
