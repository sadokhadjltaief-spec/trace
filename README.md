# TRACE

TRACE finds the exact misconception behind a student's mistake, including when the answer is right but the reasoning is wrong. It then repairs the misconception and checks mastery. See `CLAUDE.md` for the full brief and `STATUS.md` for what works today.

## Setup (Windows, PowerShell)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in GROQ_API_KEY and LLM_MODEL
.\.venv\Scripts\python.exe scripts\fetch_data.py
```
Dataset sources and licences: `data/raw/README.md`.

## Frontend
The pages in `app.py` / `pages/` are stubs. The frontend contract (shapes + rules) is in `docs/INTERFACE.md`;
fake data for building pages is in `docs/fixtures/`. Run:
```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```
Tests: `.\.venv\Scripts\python.exe -m pytest -q tests`
