# STATUS

Last update: 2026-11-21, step 6 committed.

## ⚠ BEFORE STEP 6 AND BEFORE ANY REAL DEMO
- [ ] Set `live.allow_unverified_dev: false` in `config.yaml` (now true = dev mode). Claude reminds the human at
      the start of step 6 and before the demo rehearsal.

## Step 6: tutor state machine + guards (`engine/tutor.py`, `engine/guards.py`)
- Code decides state and message type: DIAGNOSE -> HINT_1 -> HINT_2 -> HINT_3 -> RECONSTRUCT (correct retry skips
  to RECONSTRUCT; M0 -> TRANSFER). Two LLM calls per hint: structured error diagnosis (misconception fixed by
  bayes.py), then the hint of the allowed level, in the student's language. Retries graded by answer key; they do
  not update the posterior.
- Guards (pulled forward from step 7): deterministic leak (option letter, option text, SymPy value) + SymPy math
  check + style linter + ONE LLM judge call (judge model = EVAL_MODEL) for leak and congruency (misconceptions with
  posterior > 0.2). Fail closed. On failure: regenerate once, then the verified bank hint, then a template.
  Every decision logged in SQLite `guard_log`. **Judges NOT validated** (needs `eval/guard_labels.csv`, step 7).
- Demo mode: `scripts/demo_session.py --record` (live) then `scripts/demo_session.py` (offline). Checked:
  replay = 7/7 calls from cache, 0 tokens, 0 fallbacks; live recording = 7 calls, 2,778 + 1,010 tokens.
- Not done yet (step 8): RECONSTRUCT and TRANSFER grading, loops, HANDOFF. Tutor templates are English only
  (i18n = step 15), so a French student sees French LLM hints but English template lines.
- Found: reconstruction R_M1_1 step 2 says "(incorrectly) adding": the worked solution gives away the wrong step.
  Needs a bank fix (human review) before the demo.
- 75 tests pass (`tests/test_tutor.py`: leak, math, fail-closed judge, hint flow, regenerate-then-fallback,
  demo cache miss -> fallback).

## Bank review (done by the human, 2026-11-21)
- Verified: 13 questions (Q1–Q9, Q11–Q14), 8/8 reconstruction items, FR/AR names M1–M4.
- Q10 stays unverified (Eedi #795 unconfirmed). Q6 and Q14 warnings judged false alarms.

## Encoding audit (2026-11-21)
- `tests/test_encoding.py`: AST audit of every .py file; text-mode `open`, `read_text`/`write_text`,
  pandas `read_csv`/`read_json`/`to_csv`/`to_json` and `subprocess(text=True)` must pass `encoding=`.
  Found and fixed 6 (3 pandas reads, 3 subprocess calls). Also checks that bank.json / review.md / i18n files
  decode as UTF-8 and break under cp1252.

## Step 5: explanation detector (`engine/detector.py`) + real-data evaluation
- Labels M0, M1..M4, other (other = any other MAP misconception; bayes folds it into M0).
- TF-IDF (word 1-2 on question/answer/correctness tokens + explanation, char 3-5 on explanation) + LR;
  LLM few-shot (8 nearest MAP examples, same question) returns a RANKING; code converts it to a distribution
  (`detector.rank_weights`). Combined = mean. Deterministic language detection (en/fr/ar/darija) + LLM translation.
- Wired into `api.submit_answer`: free-text "Why?" -> detector -> `bayes.observe_explanation` (tau 0.5).
  Contract 1.1 adds optional `TutorTurn.explanation_evidence` (additive). TF-IDF-only fallback if the LLM fails.
- `engine/llm.py`: sliding 60 s token budget (`tpm_budget: 7000`); fixed a bug where a token-limit 429 could wait
  for the DAILY request reset (~47 min) instead of seconds. Groq free tier = 1000 requests/day + 8000 tokens/min per model.

### Measured: `results/detector.json` (REAL MAP data, seed 42, stratified 80/20)
TF-IDF on the full held-out set (7,340 rows): accuracy 0.912, MAP@3 0.955, macro-F1 0.873;
right-answer-wrong-reasoning (True_Misconception) flaw recall 0.389 (72 rows). On the 4 bank questions: acc 0.902.
400-row sample (all 72 held-out True_Misconception rows + label quotas), LLM = gpt-oss-20b, batched:
| variant | accuracy | MAP@3 | macro-F1 | TM flaw recall [95% CI] |
|---|---|---|---|---|
| TF-IDF | 0.795 | 0.893 | 0.822 | 0.389 [0.285, 0.504] |
| LLM zero-shot | 0.600 | 0.650 | 0.575 | 0.264 [0.176, 0.376] |
| LLM few-shot | 0.780 | 0.850 | 0.797 | 0.250 [0.164, 0.361] |
| combined | **0.813** | 0.887 | **0.835** | 0.319 [0.223, 0.434] |
- Honest reading: combined is best on accuracy/macro-F1 but within noise of TF-IDF. Per-class F1 for M1–M4 is
  0.88–0.98 (combined). **Weak spot: right answer + flawed reasoning is caught only ~1/3 of the time** (best:
  TF-IDF 0.39). Do not pitch that case as solved; pitch it as detected sometimes, measured, and the open problem.
- MAP@3 is over our 6 labels, not comparable to Kaggle's ~65-label leaderboard.

### Translation eval (`eval/eval_translation.py`): PAUSED
Translation eval paused due to free-tier rate limits and time constraints. Detector eval completed successfully.
Will resume if time permits.
- The run was stopped after French only; `results/translation.json` was NOT written. The log line
  (`.cache/eval_translation.log`, 100 rows, TF-IDF): fr language detection 0.99, accuracy English 0.82 ->
  French back-translated 0.86, raw French without translation 0.67. Unsaved partial run: do not cite as a result.

## Step 4: frontend contract + stub pages (final pages = teammate)
- `docs/INTERFACE.md` (contract v1.0) + `engine/contract.py` (pydantic, source of truth) + `docs/schema/*.json`
  + FAKE fixtures `docs/fixtures/*.json` (`scripts/make_fixtures.py`; MAP text + our wording only, no Eedi text).
- `engine/api.py` = the only engine module the frontend imports. Real now: sessions, diagnosis answers with
  required confidence tap, answer-key grading, IG next question, cost, read-only results. `tutor_reply`, `summary`,
  `studio_generate` raise NotImplementedError until steps 6/9/12; `engine/api_fake.py` serves fixtures with the same shapes.
- `engine/safetext.py` + minimal `engine/style.py` linter: every displayable text is a SafeText; `shown_allowed`
  is true only if leak/congruency/math/style all ran and none failed (model validator). Templates run the style linter.
- Stub pages: `app.py` (onboarding + home), `pages/1_Learn.py`, `2_Judge_Panel.py`, `3_Results.py`, `4_Report.py`,
  `5_Study_Studio.py`, helpers in `ui/`. Sidebar switch "engine / fake fixtures".
- Rules enforced by `tests/test_contract.py` (AST import scan + no file writes in app.py/pages/ui; SafeText rule;
  answer keys never in QuestionView; read_results returns a copy) and `tests/test_pages.py` (AppTest smoke of every page,
  "Targeted at:" line in Study Studio). 56 tests pass.
- Checked in the browser with the real engine: onboarding -> Learn (LaTeX renders, dev-mode warning) -> answer
  "B, sure" on Q5 -> judge panel shows M2 = 0.56 and "Next question Q7 chosen because IG = 0.263 bits".
- Run the stubs: `.\.venv\Scripts\python.exe -m streamlit run app.py`

## Step 3: diagnosis engine (`engine/bayes.py`)
- Log-space posterior over M0..M4; default likelihoods from `config.yaml` with MAP add-one-smoothed
  frequencies where MAP covers (q, h) (4 MAP questions: target h + M0). M0 = "none of M1..M4" and uses MAP rows with
  no misconception label (Correct + Neither), NOT True_Correct only (that would force P(correct|M0)~1 by selection).
- Confidence tap (wrong+sure x k_conf, wrong+unsure ^0.6, right+unsure = fragile ^0.6), explanation evidence ^tau,
  generic `update_lik()` for games/sims/flashcards, expected-IG next question with top-3, stop at 0.85 or 5 questions.
- `load_bank()` excludes questions blocked by an unconfirmed crosswalk mapping (Q10 / Eedi #795).
- 23 tests pass (incl. normalisation, log2(5) entropy, IG≈0 for a flat question, scripted M3 student >70%).

## Measured: `results/diagnosis.json` (SIMULATION PROXY, 1000 students/condition, 20% noise, 13 questions)
| condition | accuracy [95% CI] | questions used | reached 0.85 |
|---|---|---|---|
| info-gain, cap 5 | 0.643 [0.613, 0.672] | 4.51 | 50.6% |
| fixed interleaved order, cap 5 | 0.627 [0.597, 0.656] | 4.69 | 35.2% |
| random order, cap 5 | 0.537 [0.506, 0.568] | 4.81 | 19.5% |
| info-gain, no cap | 0.752 [0.724, 0.778] | 6.68 | 80.9% |
| fixed, no cap | 0.747 [0.719, 0.773] | 7.94 | 82.5% |
| random, no cap | 0.712 [0.683, 0.739] | 8.83 | 80.4% |
- Honest reading: info-gain clearly beats random; vs a well-designed fixed order its **accuracy gain is not
  significant** (CIs overlap); its real gain is reaching confidence faster (50.6% vs 35.2% within 5 questions;
  6.7 vs 7.9 questions without a cap).
- Calibration: when the engine stops at >=0.85 it is right ~80% of the time (slightly overconfident: the 20% noise
  is not in the engine's model).
- Ablation (engine without MAP frequencies): 0.626 vs 0.643. Sensitivity over 45 engine/noise configs: 0.517-0.767.
- Answers alone give ~64% at 5 questions; the explanation detector (step 5) is the planned extra evidence.

## Works
- Step 1: repo layout, config, `.venv` on **Python 3.12.0** (3.11 not installed), core packages import. `scripts/fetch_data.py` fetches and inspects MAP (HF), Eedi (manual zip), MathDial (HF), Otero (HF, licence checked first).
- `engine/llm.py` (built early, step 2 needed it): disk cache, demo mode (cache only, `CacheMiss` on miss), JSON mode, timeout, retries; **429 handling honours `retry-after` / Groq reset headers and pushes back all threads**; per-model throttle (`min_interval_s`); `batch()` for bulk evals; token log in SQLite (`.cache/trace.db`). Smoke-tested live on both models.
- Models: `LLM_MODEL=openai/gpt-oss-120b`, `EVAL_MODEL=openai/gpt-oss-20b` (Groq **free tier, rate-limited**; prices left null on purpose).
- `engine/mathcheck.py`: SymPy parsing of the LaTeX subset in MAP/Eedi, equality checking, answer-value leak detection.
- `eval/build_bank.py` -> `data/bank/bank.json` + `review.md` (both **local-only**: they contain Eedi text). Set A:
  - M1 Adding_across (MAP 307 rows; Eedi 217), M2 Duplication (704; Eedi 1976), M3 Positive (566; Eedi 1435 high, 795 medium/flagged), M4 Additive (929; Eedi 1429). See `data/bank/crosswalk.json`.
  - 14 questions (4 MAP + 10 Eedi, text-only). Answer keys and option->misconception maps come from the data: MAP by plurality of labels (>=10 rows), Eedi by labels.
  - MAP per-option label counts stored for data-driven likelihoods (step 3).
  - LLM-drafted: 3 hints/question, 8 find-the-mistake items, FR/AR names. Auto-checks with redraft (max 3): leak (value/option text/letter), false equalities, recon steps true/false as required, correct answer == start expression, variants differ.
- Tests: 9 pass (`pytest`).

## Measured
- MAP: 36,696 labelled rows, 15 questions, 403 `True_Misconception` rows (38 of them Additive = demo case "right answer, wrong reasoning").
- Bank auto-checks: 0 blocking flags; 1 warning (Q6, number "1" = answer appears in hint 3, false positive).

## Not validated / known issues
- **0 bank items verified**: waiting for human ticks in `data/bank/review.md`. Only verified items are used live.
- Redrafted per human feedback (`data/bank/redraft.json`): R_M4_1, R_M1_2, Q9 hint 1, Q14 hint 3 (Q14 hint 3 has a
  `warn`: it mentions 3/4, unavoidable since every equivalent of 9/12 has the answer's value). Notes on R_M3_1/2, Q6, Q10
  in `data/bank/review_notes.json`.
- Eedi #795 (M3) is `confirmed: false` in `crosswalk.json`: Q10 is blocked from verification and excluded from the
  engine and the benchmark until confirmed.
- Cost log: cached replays are not counted as tokens (`tests/test_llm.py`).
- Eedi licence unverified (team believes CC BY-NC 4.0): Eedi-derived files stay local-only.
- A teammate needs the raw data + Groq key to rebuild `bank.json` (it is not in git).
- Python 3.12.0 + `multiprocess` prints a harmless "Exception ignored" at exit.

## Time spent
- Step 1: ~25 min. Step 2: ~50 min. Step 2 fixes + step 3: ~45 min. Step 4 (contract + stubs): ~40 min.
- Step 5: ~1.5 h (mostly the rate-limited LLM eval). Step 6: ~35 min.
