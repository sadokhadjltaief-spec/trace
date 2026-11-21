# STATUS

Last update: 2026-11-21, after build step 1.

## Works
- Repo layout, `.gitignore`, `.env.example`, `config.yaml`, `requirements.txt`, git init.
- `.venv` on **Python 3.12.0** (3.11 is not installed; 3.12 and 3.13 are). All core packages install and import.
- `scripts/fetch_data.py`: idempotent; writes `data/raw/inspection_report.md`. Fetched MAP (HF), Eedi (manual zip), MathDial (HF), Otero (HF, licence checked first).

## Measured
- MAP: 36,696 labelled rows, 15 questions, 403 `True_Misconception` rows.
- Eedi: 1,869 questions, 2,587 misconceptions in the mapping file.

## Known issues
- Python 3.12.0 + `multiprocess` (pulled in by `datasets`) prints a harmless "Exception ignored ... _recursion_count" at interpreter exit. It's fixed in 3.12.1+. Imports work.
- `kaggle` needed `six` (added to requirements). No Kaggle credentials are on this machine, so Kaggle CLI steps are skipped.
- PyMuPDF: use `import pymupdf` (`fitz` is deprecated).
- Graphviz and Tesseract binaries are not installed (relevant to P1 only).

## Blocked / needs a human
- Eedi licence is unverified, so Eedi data is used locally only (see `data/raw/README.md`).
- `LLM_MODEL` is not set yet (needed from step 5/6). `GROQ_API_KEY` is set as a system env var.

## Time spent
- Step 1: about 25 min.
