# STATUS

Last update: 2026-11-21, after build step 3 (bank review still pending; it does not block step 3).

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
- Step 1: ~25 min. Step 2: ~50 min. Step 2 fixes + step 3: ~45 min.
