# STATUS

Last update: 2026-11-21, after build step 2 (awaiting human review of the bank).

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
- Eedi licence unverified (team believes CC BY-NC 4.0): Eedi-derived files stay local-only.
- A teammate needs the raw data + Groq key to rebuild `bank.json` (it is not in git).
- Python 3.12.0 + `multiprocess` prints a harmless "Exception ignored" at exit.

## Time spent
- Step 1: ~25 min. Step 2: ~50 min.
