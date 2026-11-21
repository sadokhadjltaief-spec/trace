# TRACE

**Other AI tutors explain. TRACE finds the exact wrong idea behind a student's mistake, even when the answer is
right, repairs that one idea with hints that never give the answer away, and proves mastery with a
find-the-mistake task and a fresh question. In French, Arabic and English, grounded in the student's own course.**

Built in 24 hours by a 2-person team for an AI-in-education competition. Every number in this README comes from
a script that wrote it to `results/`; the file is named next to it. Simulation results are labelled as such.

---

## The problem

A student writes 1/3 + 2/5 = 3/8. A generic tutor (human or AI) explains fraction addition again. But the student
does not lack the lesson: she holds one specific wrong idea, *"add the tops, add the bottoms"*. Until that idea
is found and fixed, she will repeat it. Worse, students often get the **right answer for the wrong reason**
(A/10 = 9/15 → "10 + 5 = 15 so 9 − 3 = 6"): a normal grader marks it correct and the misconception survives.

In Tunisia, families spend heavily on private tutoring (a parents' association head estimates 1.5 to 3 billion
dinars a year; an estimate, not our data). Tutors have no time to diagnose each student precisely.

## What TRACE does

1. **Diagnoses** among named misconceptions (here 4 fraction / negative-number misconceptions from real student
   data) with a **Bayesian engine**: each answer, the "sure / not sure" tap and the student's free-text "why"
   update a probability over the misconceptions. Each next question is the one with the **largest expected
   information gain**; it stops at 85 % confidence or after 5 questions.
2. **Reads the explanation**, in French, Arabic, Tunisian Darija or English: language detection, translation, and
   a detector trained on 36,696 real labelled student explanations (Kaggle MAP).
3. **Repairs** with a state machine: hint 1 (a question at the faulty step) → hint 2 (a contrasting example) →
   hint 3 (a near-complete scaffold) → **find the wrong step** in a worked solution that contains the student's
   own misconception → a **new question** of the same type. Failing twice → a 3-line **handoff note** for a human
   teacher.
4. **Refuses to teach anything false.** Every generated message passes four guards before display: answer leak
   (exact checks + LLM judge), **congruency** (does the message repeat the student's own wrong idea?), maths
   (every equality *and comparison* checked with SymPy), and style. On failure: regenerate once, then a
   human-verified fallback.
5. **Adapts how it talks, never what it diagnoses**: a "Mode clair et structuré" designed with autistic learners in
   mind (literal language, one question at a time, fixed layout "Situation / Ta tâche / Ensuite", no praise
   inflation, choose-a-reason instead of free text). Toggles chosen by the student or a parent; TRACE never infers
   a condition.
6. **Grounds the repair in the student's own course**: it indexes her PDFs locally and cites the exact page that
   covers the diagnosed misconception. Course Q&A returns passages with page numbers, or says nothing relevant was
   found; it never answers from memory.
7. **Reports** to the teacher or parent: misconception, evidence, what was tried, outcome, next step, lesson page.

## What is new

- **Diagnosis first, then teaching.** The LLM never produces a probability or a grade (except one clearly labelled
  rubric); the maths of the diagnosis is a transparent Bayesian model with real-data likelihoods.
- **Right answer, wrong reasoning** is treated as a first-class case, using the student's own words.
- **Congruency guard**: our design rationale is that a student is unlikely to notice a tutor error that matches
  her own misconception, so TRACE checks every message against the student's *current* likely misconceptions.
- **Pedagogy in code, wording by the LLM**: the state machine decides what kind of message comes next.
- **Works offline for the demo**: every LLM answer is cached; a full session replays with no network.

## Evidence (honest numbers)

| claim | number | source |
|---|---|---|
| Explanation detector, **real student data** (MAP, held-out 20 %, 7,340 explanations, our 6 labels) | accuracy **0.91**, MAP@3 0.96, macro-F1 0.87 | `results/detector.json` |
| Hard case: right answer, flawed reasoning (72 held-out rows) | caught **0.39** of the time: our open problem | `results/detector.json` |
| Faster confident diagnosis (**simulation**, 1000 students per condition, 20 % noise) | 85 % confidence within 5 questions: info-gain **50.6 %**, fixed order 35.2 %, random 19.5 % | `results/diagnosis.json` |
| Guards vs messages labelled by the team (30 messages) | **13 / 13 unsafe messages blocked**; 2 / 17 safe ones over-blocked | `results/guards.json` |
| Answer given away (**simulation**, LLM-played students, 5 per condition) | plain LLM tutor **13 / 13** messages · TRACE **0 / 13** | `results/tutor.json` |

What these numbers do **not** show, and we do not claim:
- Diagnosis *accuracy* vs a well-designed fixed question order is within noise (0.643 vs 0.627); the gain is
  speed to confidence.
- The tutor benchmark has 5 simulated students per condition: no claim about learning gains.
- No test with real students yet, and none with autistic students; the clear mode is design from established
  practice, reviewed wording still needed. `results/style.json` measures wording only.
- Not state of the art on MAP: top Kaggle entries used large fine-tuned models. Ours is a cheap detector that runs
  live inside a tutor.
- The detector's translation step for French / Arabic / Darija is built; its evaluation
  (`eval/eval_translation.py`) was paused by the free-tier token budget.

## Impact and business

- **For tutors and small centres**: TRACE is a *diagnostic layer*. It tells the tutor which idea to fix and hands
  over a one-page report and, when needed, a 3-line handoff note. The tutor's time goes where it matters.
- **For parents**: a clear report in French or Arabic: what was wrong, what was tried, what to do next.
- **Cost**: one repaired misconception used about 4k LLM tokens in our logs (free model tier; no price set, so we
  report tokens, not dinars). The diagnosis itself needs no LLM.
- **Content partners**: TRACE cites the exact lesson page of a partner site and links back instead of copying it
  (see `docs/NAJAHNI_NOTE.md`, with a French partnership email).
- **Roadmap**: Study Studio (flashcards, summaries, slides targeted at the diagnosed misconception), physics
  simulations with predict-observe-explain, more topics.

## How it is built

```
student ── Next.js frontend ──HTTP──▶ server/main.py (FastAPI, /api/v1)
                                          │
                                          ▼
                                   engine/api.py  (the only entry point; shapes in engine/contract.py)
          ┌──────────────┬──────────────┼───────────────┬──────────────┬─────────────┐
     bayes.py        detector.py     tutor.py         guards.py       rag.py       style.py / i18n
  posterior, IG   TF-IDF + LLM rank  state machine   leak, congruency  PDF pages,   profiles, linter,
  (no LLM)        + translation      (code decides)  SymPy, style     BM25 + e5    FR / AR / EN text
                                          │
                                       llm.py: every LLM call, disk cache, demo replay, retries, token log
```

- Models: `openai/gpt-oss-120b` (tutor, judge) and `gpt-oss-20b` (evaluations) on Groq; local
  `intfloat/multilingual-e5-small` for retrieval.
- Data: Kaggle MAP (real student explanations, MIT), Eedi (questions with misconception-mapped distractors; licence
  unverified, so Eedi-derived files stay local), MathDial, Otero et al. Sources and licences: `data/raw/README.md`.
- The question bank (14 questions, 8 worked solutions, 3 hints each) was drafted with the LLM, checked with SymPy
  and **approved item by item by a human** (13 questions and 8 worked solutions approved; one question waits on an
  unconfirmed misconception mapping); only approved items are used live.
- 125 automated tests (`tests/`): engine maths, guards, state machine, contract, HTTP API, retrieval, encoding.

## Run it (Windows, PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env   # GROQ_API_KEY, LLM_MODEL=openai/gpt-oss-120b, EVAL_MODEL=openai/gpt-oss-20b
.\.venv\Scripts\python.exe scripts\fetch_data.py      # datasets (see data/raw/README.md)
.\.venv\Scripts\python.exe eval\build_bank.py         # question bank (local-only) -> human review in data/bank/review.md
.\.venv\Scripts\python.exe -m pytest -q tests
```

Engine API for the frontend (OpenAPI docs at `/docs`):
```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Offline demo (replays the cached LLM answers, no network):
```powershell
.\.venv\Scripts\python.exe scripts\demo_session.py --lang fr
.\.venv\Scripts\python.exe scripts\demo_right_answer.py
```

Reproduce the results:
```powershell
.\.venv\Scripts\python.exe eval\bench_diagnosis.py   # results/diagnosis.json (no LLM)
.\.venv\Scripts\python.exe eval\eval_detector.py     # results/detector.json
.\.venv\Scripts\python.exe eval\eval_guards.py
.\.venv\Scripts\python.exe eval\bench_tutor.py --runs 5
.\.venv\Scripts\python.exe eval\eval_style.py --n 10
```

## Documents

- `docs/DEMO_SCRIPT.md`: the 5-minute demo, with the exact answers to give and a fallback plan.
- `docs/INTERFACE.md`: the frontend ↔ engine contract and its rules (no LLM call from the frontend, every text
  shown only after the guards pass).
- `docs/TEAMMATE_INSTRUCTIONS.md`: connecting the Next.js app to the engine.
- `docs/NAJAHNI_NOTE.md`: how third-party course material is used (citation only).
- `STATUS.md`: what works, what is measured, what is not validated.
