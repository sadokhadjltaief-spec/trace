# TRACE frontend ↔ engine interface (contract v1.1)

**Changelog.** 1.1 (2026-11-21): added optional `TutorTurn.explanation_evidence` (additive; 1.0 code keeps working).
1.2 (2026-11-21): added `CourseAnswer` / `CourseHit` (Course Q&A) and real `SessionSummary.lesson_refs` (additive).
1.3 (2026-11-21): added simulations: `SimItemView`, `SimRun`, `SimTurn` (additive).
1.4 (2026-11-21): added the game "Chasse aux erreurs": `GameTurn`, `GameRoundView`, `GameFeedback` (additive).
No shape change in step 6: `tutor_reply` became real for hints. After the diagnosis stops, `submit_answer` raises
`ValueError`; the page must switch to `tutor_reply` when `TutorTurn.state != "DIAGNOSE"`. A retry has
`question.requires_confidence = false`. Step 8: RECONSTRUCT shows `reconstruction.steps` (numbered from 1); its
`grading.method` is `llm_rubric` when the "why" was graded: show the label ("graded by the LLM").

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
| `submit_answer(session_id, question_id, option, confidence, explanation=None)` | `TutorTurn` | real; the last diagnosis answer returns the first tutor turn (`HINT_1`, or `TRANSFER` if M0) |
| `tutor_reply(session_id, text=None, choice=None)` | `TutorTurn` | real. `HINT_1..3`: `choice` = retried option. `RECONSTRUCT`: `choice` = number of the wrong step ("1", "2", …), `text` = why. `TRANSFER`: `choice` = option. `DONE`/`HANDOFF`: no reply (ValueError) |
| `summary(session_id)` | `SessionSummary` | fake until step 9 |
| `studio_generate(session_id, tool, source)` | `StudioOutput` | fake until step 12 |
| `misconceptions()` | `list[MisconceptionView]` | real |
| `course_index(refresh=False)` | indexing report (files, chunks, unreadable pages, flags) | real (no LLM) |
| `course_search(query, k=3)` | `CourseAnswer` | real, extractive (no LLM) |
| `list_results()` / `read_results(name)` | `list[str]` / `dict` (read-only copy) | real |

`student = {"name": str, "level": str, "lang": "fr"|"ar"|"en"}`.
`confidence` is required: `"sure"` or `"unsure"` (the UI must block submit until it is chosen).
`source` for Study Studio: `{"kind": "diagnosis"|"folder"|"pages", "folder": str?, "pages": [...]?}`.
All functions return plain dicts (`model.model_dump()`), JSON-serialisable.

## 2a. Profiles and languages (since step 10; no shape change)
- `profile` in `start_session` = toggles from `engine/profiles.yaml`, or `{"preset": "clear_structured"}`
  (toggles 1-6), optionally with overrides (`{"preset": "clear_structured", "fixed_template": false}`).
  `SessionState.profile` returns the resolved toggles. The UI name is "Mode clair et structuré" /
  "الوضع الواضح والمنظّم" / "Clear and structured mode"; never the word "autism" in the student UI.
- Engine-side toggles: `literal_language`, `one_question_per_message`, `max_words_per_sentence`, `neutral_feedback`
  (linter + prompt), `fixed_template` (the engine writes "Situation: … / Your task: … / What happens next: …" in
  `message.text`, one per line), `structured_why` (`why_options` instead of free text), `example_theme` (prompt).
- Frontend-side toggles (the engine only stores them): `visible_agenda` (show `agenda`), `visual_steps`,
  `no_timers_no_animation`, `calm_theme`, `advance_notice`.
- Every engine text is in `student.lang` (fr / ar / en): LLM hints (checked by a language guard), fixed strings
  (`i18n/tutor.json`), agenda labels, report outcome / next step, and (local bank file) question stems and worked
  solutions. `message.lang` tells you the language; render Arabic right-to-left and keep `\( … \)` maths LTR.

## 2b. HTTP (for the Next.js frontend)
`server/main.py` (FastAPI) exposes the same functions under `/api/v1` (one endpoint per function, contract
models as responses, OpenAPI at `/openapi.json`). How to connect: `docs/TEAMMATE_INSTRUCTIONS.md`.
The rules of section 1 apply to the Next.js app too: no LLM call from the frontend, render a SafeText only
when `shown_allowed` is true, no diagnosis math.

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
guard_events, explanation_evidence|null}`. Show `grading.label`; `llm_rubric` must be visibly labelled as LLM-graded.

`explanation_evidence` (since 1.1, teacher/judge panel only): `{method "combined|tfidf", lang "en|fr|ar|darija",
original, english, dist [{id "M0..M4|other", prob}], notes [str]}`. It is set when the student typed a free-text
"Why?". Show `english` next to `original` when `lang != "en"`. Do not show it in the student view in clear mode.

### SessionSummary: `docs/fixtures/session_summary.json`
`{diagnosis HypProb, diagnosis_names {id,name_en,name_fr,name_ar}, status "mastered|in_progress|handoff|no_misconception",
evidence [str], tried [state], outcome SafeText, next_step SafeText, lesson_refs [{file,page,snippet,source_url}],
handoff_note SafeText|null, calibration {sure_correct,sure_total,unsure_correct,unsure_total}, cost}`.

### StudioOutput: `docs/fixtures/studio_output.json`, `studio_output_refused.json`
`{tool, targeted_at MisconceptionView|null, sources [{file,page,timestamp}], files [{path,mime}], items [...], refused str|null}`.
`items` is tool-specific; every text inside an item is a SafeText dict. Flashcards: `{front, back, verified, misconception}`.

### CourseAnswer: `docs/fixtures/course_answer.json`, `course_answer_none.json` (since 1.2)
`{query, found, hits [{folder, file, page, snippet, lang, source_url|null, allow_derivatives, score}], note, retrieval}`.
Extractive: the hits ARE the answer. Show each snippet as a quote with "file, p. N" and the source link.
If `found` is false, show `note` and nothing else (TRACE never answers from memory). No LLM summary for now.
HTTP: `POST /api/v1/courses/search {query, k}`, `POST /api/v1/courses/index`, `POST /api/v1/courses/upload`
(multipart `files`, up to 10 files, 50 MB each, PDF/TXT/MD; saved to `data/courses/uploads/`).
`SessionSummary.lesson_refs` is now filled from the course files (lesson pages for the diagnosed misconception).

### Simulations: `docs/fixtures/sim_item.json`, `sim_turn.json` (since 1.3)
Predict → Observe → Explain. `GET /api/v1/sessions/{id}/sims` → `[SimItemView]` (no correct answer inside).
`POST …/sims/{item}/predict {option, confidence}` → `SimTurn` (stage `observe`): `grading.method = "simulation"`,
`runs` = computed series to plot (`series[].t`, `series[].y`, unit), `result_text` (show it), `posterior` =
PHYSICS posterior (ids M0..M4 are the physics bank's slots; names given). Then `POST …/sims/{item}/explain {text}`
→ `SimTurn` (stage `explain_saved`) with `next_item` = the transfer prediction; predicting it gives stage
`transfer_result`. Free exploration with sliders: `GET /api/v1/sims/templates` (JSON schema: min, max, unit per
parameter) and `POST /api/v1/sims/run {template, params}` → `SimRun` (400 if out of range). Plot with Plotly; no
animation in clear mode (`no_timers_no_animation`).

### Game "Chasse aux erreurs": `docs/fixtures/game_turn.json` (since 1.4)
`POST /api/v1/sessions/{id}/game` → `GameTurn` (round 1 of 5). The student clicks a line of `round.steps`
(1-based) and picks a reason letter → `POST …/game/answer {step, reason}` → `GameTurn` with `feedback` for that
round and the next `round` (`done` and `round = null` at the end). Show `points` / `streak` unless `calm_theme`
is on; never a timer in clear mode. A wrong reason updates the maths `posterior` (show it in the teacher view).

### GuardEvent, Cost
`GuardEvent {ts, check, status "pass|fail", action "shown|regenerated|fallback", summary}`.
`Cost {calls, cached_calls, prompt_tokens, completion_tokens, label}`. Cached replays count as calls but not tokens.
Label is "free tier, rate-limited"; no prices are shown (none configured).

## 4. Stub pages
`app.py` and `pages/` are **stubs** that show every shape working, with a sidebar switch
"Data: engine / fake fixtures". The teammate replaces them, keeping this contract and the rules above.
`ui/__init__.py` holds the display helpers (`show_text`, `latex_to_md`, `backend`) that enforce rule 4.
The frontend is `app.py`, `pages/` and `ui/`; the rules in section 1 apply to all three.
