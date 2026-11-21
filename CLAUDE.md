# TRACE — master build brief for Claude Code

You are the lead engineer on **TRACE**, built by a 2-person team (Sadok + teammate) for an
AI-in-education competition. Read this ENTIRE file before writing any code.

**Judging criteria:** (1) Innovation and creativity, (2) Technical implementation,
(3) Educational impact and business.
**Deadline:** 22 Nov 2026, 10:15 (Tunis time). About 19 hours remain when this file is
written. The last 4 hours are reserved for polish, rehearsal and submission.

---

## 0. How you must work

1. Build in the **tiers** of section 2. Do not start a tier before the previous tier's
   gate passes. P0 is what wins; P1 and P2 are bonuses.
2. After every build step: run tests, `git commit`, update `STATUS.md` (what works, what is
   measured, what is blocked, time spent) and print a summary of at most 10 lines.
3. If you are blocked for more than 15 minutes, or a decision changes the scope, **stop
   and ask**. Never silently cut or expand scope.
4. **Never invent** data, metrics, citations, URLs, licences or file contents. If something
   is missing, say so.
5. Environment: **Windows 10/11, PowerShell, Python 3.11, virtualenv in `.venv`.** Use
   `pathlib` everywhere. Give PowerShell commands when you tell the user to run something.
6. Secrets: `GROQ_API_KEY`, `LLM_MODEL` (and optional `KAGGLE_USERNAME`, `KAGGLE_KEY`,
   `HF_TOKEN`) live in `.env` (gitignored). Create `.env.example`. If a required key is
   missing, stop and ask.
7. Raw datasets, course PDFs, user videos and generated media are gitignored. Never commit
   them.
8. Verify that every package installs and imports on Windows before building on it. If a
   package fails, report it and propose an alternative; do not silently swap.

---

## 1. Product

**TRACE** finds the exact misconception behind a student's mistake, including when the
answer is right but the reasoning is wrong. It picks each next question for maximum
information, repairs the misconception with hints that never leak the answer, and proves
mastery with an error-finding task plus a fresh transfer question.

Around that core, TRACE adds:
- a **clear and structured mode** designed with autistic learners in mind (section 11)
- **curriculum grounding** in the student's own course PDFs (section 6)
- a **Study Studio** that turns the diagnosed gaps into flashcards, summaries, slides, PDFs,
  diagrams, mind maps and short narrated videos (section 12)
- **physics and mechanics simulations** with a Predict, Observe, Explain loop (section 13)
- **games** that also act as diagnostic evidence (section 14)

**The differentiator vs. generic AI study apps** (for example studera.ai, Quizlet,
Khanmigo): those apps generate generic material from whatever you upload. TRACE
**diagnoses first, then generates material that targets the diagnosed misconception.**
Every Study Studio output must show the line "Targeted at: <misconception name>" when a
diagnosis exists. This rule appears in the code, the UI and the pitch.

One-line pitch: *"Other AI tutors explain. TRACE diagnoses the exact misconception, is
validated on real student data, refuses to teach anything false, and builds every
flashcard, video and simulation around what you actually got wrong."*

Business angle (slides, not code): private tutoring in Tunisia is a very large spending
category (a parents' association head estimates 1.5–3 billion dinars per year; present it
as an estimate). TRACE is the diagnostic layer for tutors, small centres, schools and
parents. Cost per session is computed from real token counts logged by `engine/llm.py`.
The parent/teacher report and the handoff note are the business hooks. Partnering with
Tunisian content sites (for example Najahni) is part of the go-to-market story.

---

## 2. Scope tiers and gates

**P0 — must ship (target: hour 9)**
- Data pipeline (section 5) and question bank (section 7).
- Bayesian diagnosis engine + diagnosis benchmark (section 8).
- Explanation detector + real-data evaluation (section 9).
- Tutor state machine + guards (section 10).
- UI: onboarding, home, Learn view, teacher/judge live diagnosis panel, Results, Report
  (section 17).
- **Gate P0:** `pytest` green; `results/diagnosis.json` and `results/detector.json` exist
  and were produced by scripts; one full demo session runs end to end in demo mode,
  offline from cache.

**P1 — only after the P0 gate (target: hour 14)**, in this order:
1. Clear and structured mode (section 11).
2. Course-folder RAG with page citations (section 6).
3. Flashcards + summary + slides + PDF export from the Study Studio (section 12, part A).
4. Two or three physics simulations with Predict, Observe, Explain (section 13).
5. Game "Chasse aux erreurs" (section 14).
6. Confidence calibration chart, FR/AR/EN UI, handoff note (section 15).
- **Gate P1:** each feature works in the demo and has at least one test.

**P2 — only if clearly ahead:** narrated videos and podcasts (section 12, part B), video
folder ingestion (section 16), more simulations, exam autopsy from a photo.

Hard stop at hour 15: no new features after that. The remaining time is for bug fixes,
`DEMO_SCRIPT.md`, the recorded fallback video and rehearsal.

---

## 3. Non-negotiable engineering rules

1. **The LLM never produces probabilities.** All diagnosis numbers come from
   `engine/bayes.py`.
2. **Pedagogy is enforced by code.** The state machine decides the message type. The LLM
   only writes the wording.
3. **Grading is deterministic.** Multiple choice against the answer key; numeric and
   algebraic answers with SymPy; simulation predictions against the computed result. The
   only LLM grading allowed is the RECONSTRUCT explanation rubric, and the UI labels it.
4. **Every tutor-facing or generated text passes the guards** (leak, congruency, math,
   style) before it is shown. On failure: regenerate once, then use a verified fallback.
5. **Physics is computed, never generated.** Simulations come from whitelisted templates
   solved with numpy/scipy. The LLM may only pick a template and parameters inside
   validated ranges (pydantic schema).
6. **Report real numbers only.** Eval scripts write JSON to `results/`; the UI and slides
   read from there. Never hard-code a metric.
7. Every LLM call goes through `engine/llm.py`: retries, timeout, JSON mode, a disk cache
   in `.cache/llm/` (keyed by hash of model + prompt), and token/cost logging to SQLite.
   Demo mode replays from cache with no network.
8. Simulation-based results are always labelled as proxies. The detector evaluation on
   MAP is the real-data evidence.
9. Generated media states its sources (file + page). Never present generated content as
   coming from a teacher or institution.

---

## 4. Setup

Create the repo layout (section 19), `.gitignore`, `requirements.txt`, `.env.example`,
`README.md`, `config.yaml`.

Core packages: streamlit, pandas, numpy, scipy, scikit-learn, sympy, plotly, pydantic,
python-dotenv, groq, pyyaml, pytest, pymupdf, sentence-transformers, rank-bm25,
kaggle, huggingface_hub, datasets.

Study Studio packages (P1/P2, install when the step starts): python-pptx, fpdf2,
arabic-reshaper, python-bidi, matplotlib, graphviz (Python package; the Graphviz binary
may be missing on Windows — detect it and fall back to matplotlib/networkx drawing),
pyvis, edge-tts (online TTS with good French and Arabic voices), pyttsx3 (offline
fallback), imageio-ffmpeg (bundled ffmpeg binary, avoids a system install), genanki
(Anki .apkg export).

Optional: pytesseract (needs the Tesseract binary with `ara`, `fra`, `eng`),
faster-whisper. Retrieval uses numpy cosine similarity plus BM25; no vector database.

Bundle a font that supports Arabic and Latin for PDFs and images (for example Noto Naskh
Arabic + Noto Sans, both SIL Open Font License). Download them in `scripts/fetch_fonts.py`
and record the licence in `assets/fonts/README.md`.

---

## 5. Data acquisition (do as much as possible yourself)

Create `scripts/fetch_data.py` (idempotent, prints a report, never fails silently).
Try each source in order and stop at the first that works:

**A. MAP – Charting Student Math Misunderstandings** (real student explanations with
misconception labels; marked MIT on the Kaggle data page).
1. Hugging Face: `huggingface_hub.snapshot_download(repo_id="kaggle-map/data",
   repo_type="dataset", local_dir="data/raw/map")`. Inspect the layout before use.
2. Kaggle CLI: `kaggle competitions download -c map-charting-student-math-misunderstandings
   -p data/raw/map`. This needs `%USERPROFILE%\.kaggle\kaggle.json` or the env vars, AND
   the user must have clicked "accept rules" on the competition page. If you get a 403,
   tell the user exactly that and give the URL.
3. A manual zip already in `data/raw/` named `map-charting-student-math-misunderstandings*.zip`.

**B. Eedi – Mining Misconceptions in Mathematics** (questions whose wrong options map to
misconception IDs).
1. Kaggle CLI: `kaggle competitions download -c eedi-mining-misconceptions-in-mathematics
   -p data/raw/eedi` (same rules acceptance needed).
2. A manual zip in `data/raw/` named `eedi-mining-misconceptions-in-mathematics*.zip`.
Read the competition's rules page and record the data licence in `data/raw/README.md`.
If the licence does not allow it, use Eedi data only locally and do not publish derived
files.

**C. MathDial** (teacher–student tutoring dialogues, CC-BY-4.0): Hugging Face
`eth-nlped/mathdial`. Used for simulated-student prompt style and for the tutor baseline.

**D. Algebra misconceptions reference** (Otero et al., 55 misconceptions, 220 examples):
look for the official GitHub / Hugging Face release linked from arXiv 2412.03765. Verify
the repo ID and licence before downloading; use it for taxonomy descriptions only.

Unzip with Python's `zipfile`. Then **inspect and report** for every CSV: columns, row
count, dtypes, missing values, 5 random rows. For MAP also: distinct `Category` and
`Misconception` values with counts, number of `QuestionId`s, which file holds labels
(test files may be placeholders). For Eedi: number of questions with labelled distractors,
number of unique misconception IDs, 3 complete example questions with mapped misconception
names. Known facts to **verify, not assume**: MAP has `row_id, QuestionId, QuestionText,
MC_Answer, StudentExplanation, Category, Misconception`, about 36.7k labelled rows,
15 questions; Eedi has about 1,857 questions and 2,587 misconceptions.

Language caveat: MAP and Eedi are English UK school maths (grades 4–8). Tunisian course
material is Arabic and/or French. Sections 6 and 9 handle this.

---

## 6. Course material and RAG (P1)

### 6.1 Najahni.tn policy (read carefully)

Najahni (https://www.najahni.tn) is a Tunisian education site with free lessons and
exercises and paid premium PDFs. Its terms of use forbid modifying or adapting the site's
content, and the footer says all rights are reserved. Scraping is not mentioned. Therefore:

- **Do NOT crawl, bulk-download or script downloads from najahni.tn. Never bypass a login
  or paywall.**
- The user downloads a small number of free PDFs by hand (or obtains the owner's written
  permission) and puts them in `data/courses/najahni/`. Create
  `data/courses/najahni/SOURCES.md` where the user records each file's URL.
- Najahni files are used for **retrieval with citation only**: show the passage, file
  name, page number and source link. Do **not** generate adapted derivatives from them
  (summaries, flashcards, slides, videos) unless `SOURCES.md` records the owner's
  permission. The Study Studio checks a per-folder flag `allow_derivatives` in
  `data/courses/<folder>/meta.yaml` (default `false` for najahni, `true` for the user's
  own notes) and refuses with a clear message when it is false.
- Write `docs/NAJAHNI_NOTE.md` with this policy and a short partnership email template
  (French) the team can send to the site owner. The partnership is part of the business
  story.
- Never redistribute these PDFs or put them in the repo.

### 6.2 Pipeline (`engine/rag.py`, works on ANY local folder)

The user selects a folder: a "Choose folder" button opens a native dialog
(`tkinter.filedialog.askdirectory`, run in a subprocess so it doesn't block Streamlit),
with a text-input fallback. Default `data/courses/`.

1. Extract text per page with PyMuPDF. If a page yields fewer than about 50 characters,
   try OCR (pytesseract `ara+fra+eng`) if installed; else log the page as unreadable.
   Detect garbled or reversed Arabic and flag it.
2. Chunk by page/paragraph (about 300–500 tokens) with metadata: folder, file, page,
   language, `allow_derivatives`.
3. Embed with a small multilingual model (for example `intfloat/multilingual-e5-small`;
   verify it loads and handles Arabic and French). Cache embeddings by file hash.
   Retrieval = cosine top-k fused with BM25 (reciprocal rank fusion).
4. **Curriculum-grounded remediation:** after a diagnosis, retrieve the most relevant
   lesson chunks and show them with file and page. Hints may use them; guards still apply.
5. **Course Q&A page:** answers only from retrieved chunks, always cited; if nothing
   relevant is found, say so instead of answering from memory.
6. Upload zone: also accept drag-and-drop of PDF, DOCX, PPTX and TXT (limits shown under
   the zone, like "Up to 10 files · 50 MB each"). Copy uploads into `data/courses/uploads/`
   with `allow_derivatives: true`.

---

## 7. Question bank (`eval/build_bank.py` → `data/bank/bank.json`)

- **MAP-first.** Pick **4 misconceptions** (M1..M4) plus `M0 = none` from those that appear
  in MAP questions, so the detector has real training data. Prefer fractions / negative
  numbers / linear equations if MAP covers them; decide from the data and report.
- Target **12–15 questions.** MAP questions are the core; Eedi questions whose distractors
  map to the same misconceptions add variety. Keep a manual crosswalk
  `data/bank/crosswalk.json` (MAP label ↔ Eedi misconception ID); flag uncertain mappings.
- Schema:
```json
{"misconceptions":[{"id":"M1","map_label":"...","eedi_id":1234,"name_en":"...","name_fr":"...","name_ar":"...","description":"...","contrast_example":"..."}],
 "questions":[{"id":"Q1","text":"...","options":{"A":"...","B":"...","C":"...","D":"..."},"correct":"B","option_misconception":{"A":"M1","C":"M3","D":null},"map_question_id":31772,"verified_hints":["...","...","..."],"verified":true}],
 "reconstruction":[{"misconception":"M1","worked_solution":["step1","step2 (wrong)","step3"],"error_step":2,"expected_explanation":"...","verified":true}],
 "transfer":[{"misconception":"M1","question_id":"Q7"}]}
```
- Hints (3 levels), worked solutions and transfer items: draft with the LLM, check numbers
  with SymPy, write them to `data/bank/review.md` for the human to approve, and set
  `verified: true` only after approval. Only verified items are used live.
- A second, smaller bank `data/bank/physics.json` for section 13 (hand-written, see there).

---

## 8. Diagnosis engine (`engine/bayes.py`)

Hypotheses H = {M0, M1..M4}. Uniform prior unless a prior file exists.

Likelihood of option `a` on question `q` given hypothesis `h`:
- `option_misconception[a] == h` → `p_hit` (default 0.70)
- `a == correct` and `h == M0` → 0.85
- `a == correct` and `h != M0` → `p_correct_despite` (default 0.30)
- otherwise spread the remaining mass evenly; normalise per (q, h).
- If MAP covers `q`, replace the defaults with add-one-smoothed MAP frequencies and log
  which questions used data and which used defaults. All hand-set parameters live in
  `config.yaml`; the benchmark includes a sensitivity check over them.

**Confidence tap** (sure / not sure) is extra evidence: wrong + sure multiplies
misconception likelihoods by `k_conf` (1.3) and M0 by 1/k_conf; wrong + not sure raises
likelihoods to the power 0.6; right + not sure is flagged "fragile" with a small update.

**Explanation evidence:** the detector distribution is multiplied in with temperature
`tau` (0.5) so it cannot dominate alone.

**Other evidence sources** (games, simulation predictions, flashcard lapses) call the same
`update(evidence)` API with their own likelihood tables. One posterior per student.

Posterior in log space. **Next question** = argmax expected information gain
`IG(q) = H(P) − Σ_a P(a|q)·H(P | a, q)`; return the top 3 with their IG for the UI. Stop
when `max P ≥ 0.85` or after 5 questions.

Tests: posterior sums to 1; entropy of uniform over 5 = log2(5); a non-discriminating
question has IG ≈ 0; a scripted M3 student is diagnosed correctly in most runs.

---

## 9. Explanation detector (`engine/detector.py`)

Input: question, chosen option, explanation. Output: distribution over
{M0, M1..M4, other}.
1. TF-IDF (word 1–2 + char 3–5 grams) + logistic regression trained on the MAP train split.
2. LLM few-shot: retrieve the 8 most similar labelled MAP explanations for the same
   question; ask for a JSON label.
3. Combine by averaging. **Arabic, French or Tunisian Darija (Arabic or Latin script with
   digits like 3, 7, 9) input:** detect the language, translate to English with the LLM
   (cached), run the detector, keep both texts.

`eval/eval_detector.py`: stratified 80/20 split of the labelled MAP train file (fixed
seed). Report top-1 accuracy, MAP@3, macro-F1 and **recall on `True_Misconception` rows**
(right answer, flawed reasoning) for zero-shot LLM, TF-IDF, few-shot LLM and combined;
sample 400 held-out rows for the LLM variants. `eval/eval_translation.py`: translate 100
held-out explanations to French, Arabic and Darija, re-run, report the drop. Write
`results/detector.json` and `results/translation.json`.
Do not claim state of the art: top Kaggle entries exceeded 0.94 MAP@3 with large
fine-tuned models. Our claim: a cheap detector that runs live inside a tutor.

---

## 10. Tutor state machine and guards

```
DIAGNOSE -> HINT_1 -> HINT_2 -> HINT_3 -> RECONSTRUCT -> TRANSFER -> DONE
 student retries after each hint; a correct retry skips to RECONSTRUCT
TRANSFER failed -> HINT_1 with a new question for the same misconception (max 2 loops)
2 loops failed -> HANDOFF (note for the human teacher)
M0 diagnosed -> TRANSFER directly (mastery check)
```
Two-step generation each turn: (1) a structured diagnosis call (error, step,
misconception); (2) a response call that receives that diagnosis and the allowed message
type. Hint levels: 1 = a question pointing at the faulty step; 2 = a contrasting example;
3 = a near-complete scaffold without the final answer. RECONSTRUCT: show a worked solution
containing the student's misconception; the student finds the wrong step and says why.
TRANSFER: a different question for the same misconception, graded by answer key.

**Guards** (`engine/guards.py`), every decision logged to SQLite:
- **Leak guard:** deterministic check first (option letter, option text, SymPy-normalised
  value), then an LLM judge "does this reveal or trivialise the answer?".
- **Congruency guard:** an LLM judge checks the message against every misconception with
  posterior > 0.2 ("does this state, imply or exemplify misconception X?"). Rationale:
  students rarely detect tutor errors that match their own misconception.
- **Math check:** every equality claimed in a hint is verified with SymPy where parseable.
- **Style guard:** section 11.
- Judge validation: `eval/guard_labels.csv` with 30 diverse tutor messages for the HUMAN to
  label; `eval/eval_guards.py` computes judge accuracy against them. Until labelled, the UI
  must not claim the guards are validated.

---

## 11. Clear and structured mode (support profiles) (P1)

Purpose: adapt **communication style**, never the diagnosis. Based on established
practice in autism-adapted teaching: concrete and literal language, predictable
structure, visual supports, explicit expectations, reduced sensory load. Evidence for
this in LLM tutors specifically is thin, so present it as design based on established
practice, not as a treatment.

**Ethics rules (hard):**
- Never infer autism or any condition from behaviour. Never store a diagnosis.
- The UI calls it **"Mode clair et structuré" / "الوضع الواضح والمنظّم" / "Clear and
  structured mode"** with individual toggles chosen by the student or a guardian. The word
  "autism" does not appear in the student UI. Store only the toggle flags, locally.
- No therapeutic or clinical claims anywhere. A note says wording should be reviewed by a
  special-education professional or an autistic person before real use.
- Autism is not one profile: everything is a toggle; nothing is a binary type.

**Toggles** (`engine/profiles.yaml`, defaults off; the preset "clear and structured"
turns on 1–6):
1. `literal_language`: no idioms, sarcasm, metaphors, rhetorical questions.
2. `one_question_per_message` and `max_words_per_sentence` (default 15).
3. `visible_agenda`: always show "Step 2 of 5" and what happens next.
4. `fixed_template`: every turn has the same layout (Situation / Your task / What happens next).
5. `neutral_feedback`: specific, calm, no exaggerated praise, no exclamation marks.
6. `structured_why`: replace free-text "Why?" with choose-from-options reasoning or sentence starters.
7. `visual_steps`: worked steps as numbered boxes or a simple diagram.
8. `no_timers_no_animation` and `calm_theme` (muted palette, no motion, no confetti, no sounds).
9. `example_theme`: optional interest (for example "trains", "football") used as the context of examples, never changing the maths.
10. `advance_notice`: before any change of activity, show what is coming and ask "Ready?".

**Implementation:** `engine/style.py` = profile loader + deterministic **style linter**
(max words per sentence, at most one question mark, banned-idiom lists in FR/EN/AR, no
emoji, no all-caps, no "!" in neutral mode). Prompts receive the active rules; the linter
checks output, triggers one regeneration, then a template fallback. The linter also runs
on Study Studio outputs (flashcards, slides, video scripts). Animated probability bars
appear only in the teacher/judge view, never in the student view in this mode.

**Evaluation:** `eval/eval_style.py` measures compliance per toggle over 100 generated
messages with and without the profile → `results/style.json`. Do not claim improved
learning for autistic students; that requires testing with them.

---

## 12. Study Studio (`engine/studio/`)

Inspired by tool-grid study apps (Quiz, Flashcards, Summarizer, Mind maps, Slides, Podcast,
Notes from recordings). Every tool takes a **source** (a course folder selection, a set of
retrieved chunks, or the current diagnosis) and writes to `exports/<session>/`.
When a diagnosis exists, the tool targets the diagnosed misconception first and prints
"Targeted at: <misconception>". Every output lists its sources (file + page). Every
output passes the guards and the active style profile. Folders with
`allow_derivatives: false` are refused (section 6.1).

### Part A (P1)
- **Flashcards** (`flashcards.py`): sources = diagnosed misconceptions (front: a tricky item
  that triggers the misconception; back: correct reasoning plus why the wrong idea fails),
  and course chunks (definition/formula cards with page citation). LLM drafts, SymPy
  verifies numeric content, unverified cards wait in a review screen. Scheduling: Leitner
  boxes or SM-2 in SQLite. Review page: front, reveal, self-rate (again / hard / good /
  easy), no timers in clear mode. A lapse on a misconception card is evidence for
  `bayes.update`. Export: Anki `.apkg` (genanki) and TSV.
- **Summary / résumé** (`summary.py`): structured summary of selected chunks with a
  citation after each bullet; "key formulas" and "common mistakes" sections, the second
  filled from the diagnosis. Export Markdown and PDF.
- **Quiz** (`quiz.py`): only from the verified bank (deterministic answer keys). Never let
  the LLM invent answer keys for graded questions.
- **Slides** (`slides.py`): python-pptx deck (6–10 slides): title, concept, the student's
  misconception vs the correct idea (side by side), worked example, practice question,
  summary, sources slide. Same theme as the app. Arabic slides right-to-left.
- **PDF** (`pdf.py`): fpdf2 with the bundled fonts; Arabic shaped with arabic-reshaper +
  python-bidi. Used for summaries, the parent/teacher report and worksheets (questions on
  page 1, answer key on page 2).
- **Diagrams and images** (`diagrams.py`): generated programmatically: number lines,
  fraction bars, area models, force diagrams, function graphs (matplotlib), and concept or
  mind maps (graphviz, or a pyvis interactive HTML fallback). No AI image generation: it
  can draw wrong maths. If the user later supplies an image API key, an optional
  decorative-illustration step may be added, never for content that carries meaning.

### Part B (P2)
- **Narrated explainer video** (`video.py`): the LLM writes a script of 5–8 scenes (each:
  narration ≤ 40 words + a slide or diagram spec). Render each scene as a PNG (same code as
  slides/diagrams), synthesise narration with edge-tts (FR/AR/EN voices; fallback pyttsx3
  offline), and assemble with ffmpeg from imageio-ffmpeg (image + audio per scene, then
  concatenate; burn in subtitles). Output MP4 + SRT. Target ≤ 90 seconds. Cache by script
  hash. In clear mode: no transitions, slower narration, subtitles on.
- **Podcast** (`podcast.py`): the same script as a 2-voice audio dialogue (MP3).
- Optional if time allows: math animations with Manim (only if it installs cleanly on
  Windows without LaTeX problems; otherwise skip and say so).

---

## 13. Simulations for physics and mechanics: Predict, Observe, Explain (P1: 2–3 sims; P2: more)

This extends the diagnosis to science, using the **Predict–Observe–Explain** method:
1. **Predict:** a multiple-choice prediction whose wrong options map to physics
   misconceptions (+ the confidence tap). This updates the Bayesian posterior exactly like
   a question.
2. **Observe:** the student runs an interactive simulation (Plotly animation with
   Streamlit sliders) and sees the result.
3. **Explain:** the student explains the difference between prediction and result
   (free text or structured), then gets a transfer prediction with different parameters.

`engine/sims/`: each simulation is a whitelisted template with a pydantic parameter schema
(ranges and units) and a solver in numpy/scipy (`solve_ivp`). Unit tests check physics
against analytic solutions (for example the period of a small-angle pendulum, the
projectile range on flat ground, energy conservation without friction).

Templates (build in this order; stop when time runs out):
1. `free_fall` with optional air drag: misconception "heavier objects always fall faster".
2. `pendulum`: misconception "the period depends on the mass".
3. `cart_force` (Newton's 2nd law, friction toggle): misconceptions "motion needs a
   constant force", "no force means no motion".
4. `projectile`: misconception "a horizontally launched ball falls more slowly".
5. `inclined_plane` with friction; 6. `spring_mass`; 7. `rc_circuit` / Ohm's law:
   misconception "current is used up by the bulb".

Write `data/bank/physics.json` by hand (misconceptions, prediction questions, mapped
options, transfer predictions) and put it through the same human review as the maths bank.
Do NOT copy items from copyrighted concept inventories (for example the Force Concept
Inventory); write original items. The LLM may suggest which template and parameters fit a
course chunk, but the parameters are validated by the schema, and the result is always
computed.

---

## 14. Games (P1, plus a P2 extra)

- **"Chasse aux erreurs"** (default topics: the 4 maths misconceptions, configured in
  `games.yaml`): 5 rounds; each shows a worked solution with exactly one faulty step (reuse
  verified `reconstruction` items; LLM variants verified with SymPy and approved by a
  human). The student clicks the faulty line, then picks the reason from 3 options (one
  correct; the distractors are other misconceptions). Points and a streak counter. **No
  timer in clear mode.** A wrong reason matching misconception M is evidence for M.
- **P2: "Prédis la simulation"**: 5 quick physics predictions in a row, scored, each one
  followed by the animation. Same evidence rule.
- Home dashboard shows streak and points (as in study apps), but these are switched off
  by the `calm_theme` toggle.

---

## 15. Other features (P1)

- **Confidence calibration chart:** how often "sure" answers were right (Plotly).
- **Trilingual UI:** FR / AR / EN strings in `i18n/`; Arabic right-to-left via injected
  CSS (`direction: rtl`), with maths kept left-to-right. Tunisian Darija accepted as input.
- **One-page report** for teacher or parent (FR / AR / EN): misconception found, evidence,
  what was tried, outcome, suggested next step, relevant lesson page. Markdown + PDF.
- **Handoff note** (3 lines for a human tutor) triggered by HANDOFF.

---

## 16. Video folder ingestion (P2 only)

"Videos" here means two things; build them separately:
- **Generating** videos: section 12 part B.
- **Ingesting** the user's own lesson videos from a selected local folder: scan for mp4,
  mkv, webm, mp3, wav, m4a; extract audio with the imageio-ffmpeg binary; transcribe with
  Groq Whisper (`whisper-large-v3-turbo`) if available, else faster-whisper locally; cache
  by file hash; chunk with timestamps; index in the same RAG store; cite with timestamps;
  allow flashcards/summary from them (they are the user's own files).

---

## 17. UI (`app.py`, Streamlit multipage, custom CSS)

Layout patterns to borrow from modern study apps (screenshots in
`docs/inspiration/`; read them with your image tool if present). Copy the **patterns**,
never another product's name, logo or exact branding:
- **Onboarding** (3–4 screens, progress bar on top, one big question per screen, large
  input, "Continue →" button): name, level/class, language (FR / AR / EN), "How do you like
  explanations?" (this is where the clear and structured preset is offered, as a neutral
  preference, with the individual toggles under "Customise").
- **Home**: greeting ("Bonjour, <name>"), a row of large cards: *Diagnose me*, *Continue
  learning*, *Study Studio*, *Simulations*, *Chasse aux erreurs*, *Course Q&A*; then
  "Your gaps" (diagnosed misconceptions with status) and "Due for review" (flashcards).
- **Study Studio page**: a grid of tool cards (icon, title, one-line description), like
  Quiz / Flashcards / Summary / Slides / PDF / Mind map / Video / Podcast / Simulation;
  each opens a form "Source: [diagnosis | course folder | selected pages]".
- **Upload zone**: dashed rounded box, cloud icon, "Drop your files here or Choose files",
  limits shown underneath.
- Sidebar: navigation, language, support-profile toggles, course-folder picker, demo-mode
  switch, light/dark.
- Visual style: rounded cards (12–16 px radius), soft shadows, generous whitespace, one
  accent colour (choose our own, for example deep teal) with a light gradient on the
  primary button. In `calm_theme`: muted palette, no gradients, no animation.

Pages:
- **Learn** (student view): question, options, Sure / Not sure toggle required before
  submit, "Why?" input (free text or structured), tutor chat, agenda (in clear mode).
- **Teacher / Judge view**: live diagnosis panel (probability bars for M0..M4), "Next
  question chosen because IG = … bits (alternatives …)", state-machine state, guard events
  ("1 hint blocked: revealed answer"), session cost.
- **Study Studio**, **Simulations**, **Chasse aux erreurs**, **Flashcards**, **Course Q&A**
  (P1), **Report**, **Results** (reads `results/*.json`, shows every number with the
  script that produced it).
- **Demo mode**: fixed seed, pre-filled student, LLM answers and generated media served
  from cache so the demo works offline. Write `docs/DEMO_SCRIPT.md` (5 minutes: problem and
  market → live diagnosis including the right-answer-wrong-reasoning case → catch your own
  mistake → one Study Studio output targeted at the misconception → one simulation →
  clear-mode switch → results slide → business slide) and a recorded-fallback checklist.

---

## 18. Benchmarks (all write to `results/`)

- `bench_diagnosis.py` (no LLM; 1000 simulated students per condition): simulated
  students sample answers from the likelihood table mixed with 20% uniform noise. Info-gain
  vs fixed order vs random order. Mean questions to reach 0.85, diagnosis accuracy, 95%
  CIs, hyperparameter sensitivity. → `diagnosis.json`
- `eval_detector.py`, `eval_translation.py` → `detector.json`, `translation.json`.
- `bench_tutor.py` (LLM-played students, 30–50 runs per condition; prompts plant one
  misconception, keep it unless genuinely corrected, use real MAP explanations as style
  examples): (A) plain tutor, (B) TRACE without guards, (C) full TRACE. Leak rate
  (deterministic), transfer pass rate (answer key), turns. Labelled as simulation proxy.
  → `tutor.json`
- `eval_guards.py`, `eval_style.py` → `guards.json`, `style.json`.
- `eval_studio.py` (P1): for 20 generated flashcards/summaries, % passing SymPy checks and
  % with valid citations → `studio.json`.
- `test_sims.py`: physics checks against analytic solutions (part of pytest).
- `cost.json`: tokens and cost per session from the logs and prices in `config.yaml`
  (the user supplies current prices).

---

## 19. Repository layout

```
CLAUDE.md  STATUS.md  README.md  config.yaml  .env.example  requirements.txt
scripts/   fetch_data.py fetch_fonts.py
data/raw/  data/bank/  data/courses/<folder>/meta.yaml   (raw, courses gitignored)
docs/      NAJAHNI_NOTE.md DEMO_SCRIPT.md inspiration/
assets/    fonts/ icons/
engine/    llm.py bank.py bayes.py detector.py tutor.py guards.py style.py profiles.yaml
           mastery.py rag.py report.py
           studio/ flashcards.py summary.py quiz.py slides.py pdf.py diagrams.py video.py podcast.py
           sims/   base.py free_fall.py pendulum.py cart_force.py projectile.py ...
           game.py
eval/      build_bank.py eval_detector.py eval_translation.py bench_diagnosis.py bench_tutor.py
           eval_guards.py eval_style.py eval_studio.py guard_labels.csv
results/  i18n/  exports/  games.yaml
app.py  pages/  tests/
```

---

## 20. Build order (commit after each step; stop at gates)

**P0**
1. Setup + `fetch_data.py` + inspection report + `data/raw/README.md`. Show me the report, then continue.
2. `build_bank.py` + crosswalk + `review.md`. Ask me to approve the review items.
3. `bayes.py` + tests + `bench_diagnosis.py` (first real result).
4. Streamlit skeleton: onboarding, home, teacher/judge live panel driven by the engine (no LLM yet).
5. `detector.py` + `eval_detector.py` (+ translation test).
6. `llm.py`, `tutor.py`, hint generation, demo mode.
7. `guards.py` wired in; create `guard_labels.csv` for me to label.
8. RECONSTRUCT, TRANSFER, mastery, HANDOFF; `bench_tutor.py`.
9. Report and Results pages. **Gate P0.**

**P1**
10. `style.py` + profiles + `eval_style.py`.
11. `rag.py` + `NAJAHNI_NOTE.md` + folder picker + course Q&A + remediation links.
12. Study Studio part A: flashcards (+ review + Anki export), summary, slides, PDF, diagrams.
13. Simulations 1–3 with Predict, Observe, Explain + `physics.json` (ask me to review it).
14. Chasse aux erreurs.
15. Calibration chart, i18n FR/AR/EN, trilingual report. **Gate P1.**

**P2** (only if ahead): narrated video + podcast, video folder ingestion, more
simulations, "Prédis la simulation", exam autopsy.

**Final 4 hours:** README, `DEMO_SCRIPT.md`, slide-ready numbers exported from `results/`,
full rehearsal in demo mode, recorded fallback. No new features.

**Definition of done:** the demo runs offline from cache; every number in the UI or slides
traces to a script in `results/`; `STATUS.md` states honestly what is validated and what
is not.
