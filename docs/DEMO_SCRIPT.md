# TRACE: 5-minute demo script (jury)

Every number below comes from a file in `results/` produced by a script; the file is named next to it.
Say "simulation" when a number comes from simulated students. Video and podcast are not built: do not show them.

---

## Before the demo (T-30 min checklist)

- [ ] **`config.yaml`: set `live.allow_unverified_dev: false`** (only human-verified bank items in use).
- [ ] Tests green: `.\.venv\Scripts\python.exe -m pytest -q tests`
- [ ] Cache replays offline (0 tokens, 0 fallbacks expected for FR and AR):
  ```powershell
  .\.venv\Scripts\python.exe scripts\demo_session.py --lang fr
  .\.venv\Scripts\python.exe scripts\demo_session.py --lang ar
  .\.venv\Scripts\python.exe scripts\demo_right_answer.py
  ```
- [x] Clear mode recorded (2026-11-21, ~6.2k tokens): hint 1 LLM-written; hint 2 = safe fallback (style guard).
      Check its replay: `.\.venv\Scripts\python.exe scripts\demo_session.py --lang fr --profile clear`
- [ ] Engine up in offline demo mode: `$env:TRACE_DEMO="1"` then
      `.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000`
      (check `http://127.0.0.1:8000/api/v1/health`), then the Next.js app (`pnpm dev`).
- [ ] Start the session with **`demo: true`** (LLM answers replayed from cache: works with no network).
- [ ] Course PDFs (own notes, or Najahni free PDFs downloaded by hand with URLs in `SOURCES.md`) in
      `data/courses/<folder>/`, then `POST /engine/courses/index`. Without PDFs, skip step 6.
- [ ] Two windows: **student view** (Learn) and **teacher / judge view** (posterior bars, IG, guard events, cost).
- [ ] Fallback video recorded (see the end) and on the desktop.

The demo student is **Amira, 7e, French**. She answers like a student who "adds the tops and the bottoms" (M1).
Script answers (match the cache exactly):
1. First question Q5 (2/3 × 5): option **A**, **Sûr**, "Pourquoi ?" =
   `j'ai additionné les numérateurs ensemble et les dénominateurs ensemble`
2. Next question Q1 (1/3 + 2/5): option **C** (3/8), **Sûr**, no explanation. → diagnosis stops.
3. Hint 1 → retry **A** (wrong). Hint 2 → retry **D** (correct).
4. Find the wrong step: **step 2**, "Pourquoi ?" = `on ne peut pas additionner les dénominateurs`
5. New question Q2: the correct option.

---

## 0:00 – 0:40 · The problem

> "In Tunisia, families spend a lot on private tutoring: a parents' association head estimates 1.5 to 3 billion
> dinars a year. Most tutoring, human or AI, *explains again*. But a student who gets 1/3 + 2/5 = 3/8 does not
> need the lesson again: she needs someone to find the exact wrong idea, 'add the tops, add the bottoms', and fix
> that one idea. TRACE does that."

(Present the market figure as an estimate, with its source as stated.)

## 0:40 – 1:40 · Live diagnosis (student view + judge view)

- Amira answers Q5 with **A**, taps **Sûr**, writes her reason **in French**.
- Judge view: the explanation detector translated it ("I added the numerators together and the denominators
  together") and the bars move toward **M1**. Point at: *"Next question chosen because IG = … bits"*.
  > "Every number here is computed by a Bayesian engine, not by the LLM. It picks the question that will teach it
  > the most about Amira."
- Q1: she chooses 3/8, sure. **M1 = 0.89** → the engine stops: it is confident.
- Evidence to quote (`results/diagnosis.json`, **simulation**, 1000 simulated students per condition): within
  5 questions, choosing by information gain reaches 85 % confidence for **50.6 %** of students, vs 35.2 % for a
  fixed order and 19.5 % for random order. (Accuracy vs the fixed order is within noise: say "diagnoses with fewer
  questions", not "more accurate".)

## 1:40 – 2:20 · Right answer, wrong reasoning

Run `scripts\demo_right_answer.py` (or show it on the judge view). Two students pick the **correct** answer 6 for
A/10 = 9/15, both sure:

- Student A: "because 10 + 5 = 15 so you do 9 - 3 = 6" → detector: **additive reasoning (M4) 0.98**. The engine is
  *not* convinced she is fine (M0 only 0.38) and keeps asking.
- Student B: "I divided 15 by 5 and 10 by 5, so 3 times 2 is 6" → **M0 0.96**; engine 0.85 sure → stops.
> "Same right answer. A grader says both are fine. TRACE sees that one of them got it right for the wrong reason."

Evidence (`results/detector.json`, **real student data**: Kaggle MAP, 36,696 labelled explanations, held-out
20 %): the detector finds the right label **91 %** of the time (our 6 labels, 7,340 held-out explanations,
macro-F1 0.87; not comparable to the Kaggle leaderboard, where top entries used large fine-tuned models).
Honest limit: on the hard case "right answer, flawed reasoning" it catches **about 1 in 3** (0.39 recall on 72
rows). Say it: "This is the open problem; we measure it instead of hiding it."

## 2:20 – 3:20 · Repair, safely

- Hint 1 (French): a question pointing at the wrong step. Amira retries, still wrong. Hint 2: a contrasting
  example with other numbers. She gets it right.
  > "The state machine decides what kind of message comes next; the LLM only writes the words. Then four guards
  > check every message before the student sees it: does it give away the answer, does it repeat the student's
  > own wrong idea, is every equality and comparison true (checked with SymPy), is the style right."
- Evidence: `results/guards.json`: on 30 tutor messages labelled by the team, **every unsafe message was
  blocked (13 of 13)**; 2 of 17 safe ones were over-blocked. `results/tutor.json` (**simulation**, 5 simulated
  students per condition): a plain LLM tutor gave the answer away in **13 of 13** messages; TRACE in **0 of 13**.
  (Do not claim better learning from that run: n = 5.)
- **Find the mistake:** a worked solution with one wrong step (it contains her own misconception). She picks
  step 2 and says why → "explanation graded by the LLM" (that label is on screen; it is the only LLM grading).
- **New question** of the same type → correct → **mastered**.

## 3:20 – 3:50 · Clear and structured mode

Switch the profile to "Mode clair et structuré" (`{"preset": "clear_structured"}`, demo mode) and start a new
session. **Recorded answers for this mode** (different from the default run: in clear mode the "why" is a choice,
not free text, so the diagnosis needs 4 questions):
Q5 **A** sûr · Q1 **C** sûr · Q11 **A** sûr · Q2 **B** sûr → hint 1 (LLM) → retry **C** (wrong) → hint 2 → retry
**A** (correct) → find the wrong step: **step 2** + any reason → new question Q3: **C** (4/5) → mastered.
Hint 2 is the safe fallback sentence: the style guard blocked two LLM drafts because a sentence had more than
15 words. Show it as the guard at work ("in clear mode, a sentence longer than 15 words is never shown").

Then show:
every message has the same three lines (Situation / Ta tâche / Ensuite), one question at a time, short sentences,
no praise words, choose-a-reason instead of free text. Probability bars stay in the teacher view only.
> "Designed with autistic learners in mind, from established practice. It changes how TRACE talks, never the
> diagnosis. It is a set of choices the student or a parent turns on; TRACE never guesses a condition."
Do not claim learning gains (`results/style.json` measures wording only and shows no difference on raw wording;
the rules are enforced by code).

## 3:50 – 4:15 · The student's own course + the report

- Report page: misconception found, the evidence (each answer, the explanation, the hints, the wrong step found),
  outcome, next step, **the page of her own course PDF** that covers it (file + page + link). If a teacher must
  take over, a 3-line handoff note.
- Course Q&A: a question → the passage from her own PDF with the page. If nothing is relevant, TRACE says so
  instead of answering from memory.
> "Najahni-style content stays theirs: we cite the page and link back; no copying, no derivatives without
> permission. That is our partnership pitch."

## Optional (if time, replaces part of 3:50 – 4:15) · Study Studio, simulation, game

All offline: the Study Studio outputs for Amira (FR, M1) are cached; simulations, game and report use no LLM.
- Study Studio → **Flashcards** / **Slides** (cached for Amira after the recorded run; check it in rehearsal): every output says **"Ciblé sur : Additionne les numérateurs et
  additionne les dénominateurs"** and lists its sources. Flashcards wait for a teacher's approval before use.
- Simulations → S1 (two balls, 1 kg and 5 kg, no air): predict "the heavier one", watch them land together
  (computed by scipy, not generated); the physics bars move to "heavier objects always fall faster".
  **Needs the physics items ticked in `data/bank/physics_review.md`** (allow_unverified_dev is false).
- Chasse aux erreurs: one round, click the wrong line, choose the reason.
- Report → PDF in French and Arabic, with the confidence chart.

## Optional · "Demander au tuteur" and "Plan d'étude" (offline, cached)

- In the tutor, on a NEW conversation (not during a diagnosis), type:
  `5*8` → "5 × 8 = 40", computed exactly by the engine (no LLM).
  `Comment additionner deux fractions ?` → answer from the course with "(cours_fractions_relatifs.pdf p.1)".
  `Explique-moi le théorème de Pythagore` → tutor answer, labelled "pas tirée de ton cours".
  `Qui va gagner la Coupe du monde de football ?` → "Je suis un tuteur éducatif, je ne peux répondre qu'aux
  questions sur tes cours."
- Plan d'étude → upload `C:\TRACE\docs\demo\cours_fractions_relatifs.pdf`, leave the details empty, confirm →
  5 days ("Étudier : Chapitre 1 …" to chapter 4, then a review), with durations, concrete tasks, key formulas and
  self-check questions.
- Exact wording matters for the cache: other questions still work offline but fall back (course passages instead of
  a written answer; a plan built by code, one page per day).

## 4:15 – 4:40 · Results slide (read from `results/`)

| what | number | source |
|---|---|---|
| explanation detector, real MAP data | 91 % top-1, MAP@3 0.96 | `detector.json` |
| right answer, flawed reasoning caught | ~1 in 3 (open problem) | `detector.json` |
| faster confident diagnosis (simulation) | 50.6 % vs 35.2 % (fixed) within 5 questions | `diagnosis.json` |
| unsafe tutor messages blocked | 13 / 13 (30 labelled messages) | `guards.json` |
| answer given away (simulation, n = 5) | plain tutor 13/13 · TRACE 0/13 | `tutor.json` |

## 4:40 – 5:00 · Business

> "TRACE is the diagnostic layer for tutors, small centres, schools and parents: it tells a tutor *which* idea
> to fix and hands over a one-page report and a handoff note. One repaired misconception costs about 4k LLM tokens
> on a free model tier (measured from our logs; no price set). The Study Studio already turns the diagnosed gap
> into flashcards, slides and worksheets; next are narrated videos, more topics, and partnerships with Tunisian
> content sites."

---

## If something breaks

| problem | do this |
|---|---|
| no network / Groq down | nothing to do if the session was started with `demo: true` (cache). |
| a hint shows the generic sentence "Relis chaque étape…" | the path left the recorded script; keep going (it is the verified fallback); say "this is the safe fallback". |
| Next.js app fails | open `http://127.0.0.1:8000/docs` and run the calls there, or run `scripts\demo_session.py --lang fr` in a terminal (shows every turn). |
| engine restarted | sessions are in memory: start a new session. |
| everything fails | play the recorded video. |

## Recorded fallback video (record once, before the demo)

1. Screen-record the full 5 minutes with the cache (demo mode), FR student view + judge view side by side.
2. Include the terminal run of `scripts\demo_right_answer.py`.
3. Keep it under 5 minutes, 1080p, on the desktop and on a USB key.
