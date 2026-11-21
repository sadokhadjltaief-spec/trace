# Connecting the Next.js frontend to the TRACE engine (FastAPI)

For the frontend repo (`TRACE_frontend_temp`). The engine side is in `C:\TRACE` (`server/main.py`).
Contract: `docs/INTERFACE.md` (v1.1). Live schema of every shape: `http://127.0.0.1:8000/docs` and `/openapi.json`.

## Why the current chat route must go

`app/api/chat/route.ts` calls an LLM directly (`streamText`, `openai/gpt-5.4-mini`). That bypasses everything
TRACE is judged on: the Bayesian diagnosis, the state machine (which decides the type of each message), and the
guards (leak, congruency, math, style) that check every text **before** it is shown. Rules 2–4 of
`docs/INTERFACE.md` forbid it. After this change the frontend makes **no LLM call and holds no model key**.

Streaming is not possible on purpose: the guards need the whole message before anything is displayed.
Show a "thinking" state while a request runs (a hint turn takes about 2–10 s on the free tier; cached demo turns are instant).

## 1. Start the engine

```powershell
cd C:\TRACE
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```
Check: `http://127.0.0.1:8000/api/v1/health` returns `{"ok": true, "contract_version": "1.1", ...}`.
One worker only (sessions are in memory). Restarting the server forgets all sessions.

## 2. Proxy `/engine/*` to FastAPI (no CORS, no URL in client code)

`next.config.mjs`:
```js
const nextConfig = {
  typescript: { ignoreBuildErrors: true },
  images: { unoptimized: true },
  async rewrites() {
    return [{ source: '/engine/:path*', destination: 'http://127.0.0.1:8000/api/v1/:path*' }]
  },
}
export default nextConfig
```
(CORS for `http://localhost:3000` is also enabled on the server, if you prefer calling port 8000 directly.)

## 3. Replace `app/api/chat/route.ts`

Delete the `streamText` / `buildInstructions` code and the `ai` imports. If you still want a server route (for
example to keep one endpoint name), make it a plain proxy with **no logic**:

```ts
// app/api/chat/route.ts — thin proxy to the TRACE engine. No LLM, no prompt, no text generated here.
const ENGINE = process.env.TRACE_ENGINE_URL ?? 'http://127.0.0.1:8000/api/v1'

type Action =
  | { action: 'start'; student: { name: string; level: string; lang: 'fr' | 'ar' | 'en' }; profile?: Record<string, unknown>; demo?: boolean }
  | { action: 'answer'; sessionId: string; question_id: string; option: string; confidence: 'sure' | 'unsure'; explanation?: string }
  | { action: 'reply'; sessionId: string; choice?: string; text?: string }
  | { action: 'state' | 'summary'; sessionId: string }

export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as Action | null
  if (!b || !('action' in b)) return Response.json({ error: 'Invalid request' }, { status: 400 })
  const sid = 'sessionId' in b ? encodeURIComponent(b.sessionId) : ''
  const call = (path: string, body?: unknown) =>
    fetch(`${ENGINE}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  let r: Response
  switch (b.action) {
    case 'start':   r = await call('/sessions', { student: b.student, profile: b.profile ?? {}, demo: b.demo ?? false }); break
    case 'answer':  r = await call(`/sessions/${sid}/answer`, { question_id: b.question_id, option: b.option, confidence: b.confidence, explanation: b.explanation ?? null }); break
    case 'reply':   r = await call(`/sessions/${sid}/reply`, { choice: b.choice ?? null, text: b.text ?? null }); break
    case 'state':   r = await call(`/sessions/${sid}`); break
    case 'summary': r = await call(`/sessions/${sid}/summary`); break
  }
  return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } })
}
```
Remove `@ai-sdk/react` / `ai` from the tutor if nothing else uses them, and any model key from `.env.local`.

## 4. The tutor component: from free chat to TRACE turns

`useChat` expects a streamed chat protocol; replace it in `components/dashboard/tutor/tutor-chat.tsx` with plain
state. The loop:

1. `start` → `SessionState`. Show `current_question` (text + option buttons). Show `warnings` (dev-mode notice).
2. The student picks an option **and** taps Sure / Not sure (**required**: disable Submit until chosen),
   optional "Why?" text → `answer` → `TutorTurn`.
3. While `turn.state === 'DIAGNOSE'`: show `turn.question` and repeat step 2.
4. After that, always send `reply`, depending on `turn.expects`:

| `turn.expects` | show | send |
|---|---|---|
| `retry` (HINT_1..3) | `turn.message` + `turn.question` options (no confidence tap: `requires_confidence` is false) | `reply {choice: "B"}` |
| `error_step` (RECONSTRUCT) | `turn.message` + numbered `turn.reconstruction.steps` (1-based) + a "why" box | `reply {choice: "2", text: "why"}` |
| `transfer_answer` (TRANSFER) | `turn.message` + `turn.question` options | `reply {choice: "C"}` |
| `none` (DONE / HANDOFF) | `turn.message`, then a link to the report | `summary` |

**Displaying text (rule 4):** render `message.text` **only if `message.shown_allowed` is true**; otherwise show a
neutral "message withheld" line. Never edit, translate or re-generate engine text in the frontend.
Show `turn.grading.label` after each answer; when `grading.method === 'llm_rubric'` it must stay visible
(it says the explanation was graded by the LLM).

**Never compute anything** from `posterior`, `ig_bits`, etc. (rule 2): display them as given, in the teacher/judge
view only. Do not show probability bars to the student in clear mode.

Minimal client helper (`lib/engine.ts`):
```ts
export async function engine<T>(body: Record<string, unknown>): Promise<T> {
  const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `engine error ${r.status}`)
  return r.json() as Promise<T>
}
export type SafeText = { text: string; lang: 'fr' | 'ar' | 'en'; origin: 'llm' | 'verified_bank' | 'template'; shown_allowed: boolean; fallback_used: boolean }
export type QuestionView = { id: string; text: string; options: Record<string, string>; requires_confidence: boolean; why_mode: 'free' | 'structured' }
export type TutorTurn = {
  state: 'DIAGNOSE' | 'HINT_1' | 'HINT_2' | 'HINT_3' | 'RECONSTRUCT' | 'TRANSFER' | 'DONE' | 'HANDOFF'
  message: SafeText
  expects: 'answer' | 'retry' | 'error_step' | 'explanation' | 'transfer_answer' | 'none'
  question: QuestionView | null
  reconstruction: { id: string; problem: string; steps: string[] } | null
  grading: { correct: boolean | null; method: string; label: string }
  agenda: { step: number; total: number; next: string }
}
```
Full types: generate them from `/openapi.json` with any OpenAPI-to-TypeScript tool if you want; the hand-written
subset above is enough for the tutor.

Question and option text contain LaTeX `\( … \)`: render with your Markdown + KaTeX (convert `\(…\)` to `$…$`).

## 4b. Clear and structured mode and languages

Send the onboarding choice as `profile` in `start`: `{"preset": "clear_structured"}` for "Mode clair et structuré",
or individual toggles (see `docs/INTERFACE.md` 2a). With `fixed_template` the engine already writes the three
lines "Situation / Ta tâche / Ensuite" into `message.text` (render the newlines). The engine answers in
`student.lang`; render `message.lang == "ar"` right-to-left.

## 5. Errors

| HTTP | meaning | frontend |
|---|---|---|
| 400 | wrong action for the current state (e.g. `answer` after the diagnosis ended) | follow `turn.expects` |
| 404 | unknown session (server restarted) | start a new session |
| 422 | request shape wrong (e.g. confidence missing) | fix the request |
| 501 | not built yet (Study Studio) | show "coming soon" |

## 6. Demo mode

`start` with `demo: true` replays LLM answers from the engine cache (offline, 0 tokens). The recorded demo
student answers like `scripts/demo_session.py` (French or Arabic, "adds numerators and denominators").
A different path in demo mode falls back to verified bank text (still correct, just not the recorded wording).

## 6b. Course Q&A and uploads (since contract 1.2)

- Upload zone: `POST /engine/courses/upload` (multipart form, field `files`; up to 10 files, 50 MB each, PDF / TXT /
  MD; show these limits under the zone). Files go to `data/courses/uploads/` and are re-indexed.
- Search: `POST /engine/courses/search {"query": "...", "k": 3}` → `CourseAnswer`. Show each hit as a quote with
  "file, p. N" and its `source_url`. If `found` is false, show `note` only.
- The folder picker of the brief is a desktop dialog; in the web app, use the upload zone instead.

## 6c. Simulations (since contract 1.3)

Simulations page: list `GET /engine/sessions/{id}/sims`; for each item show the text, the options and the Sure /
Not sure tap → `POST /engine/sessions/{id}/sims/{item}/predict`. Then plot `runs[*].series` (Plotly, one line per
object a/b), show `result_text` and `grading.label`, ask "why?" → `POST …/explain {text}` → show `next_item` (the
transfer prediction) and predict it the same way. Sliders: `GET /engine/sims/templates` gives min/max/unit per
parameter; `POST /engine/sims/run` recomputes. Never compute physics in the frontend.

## 6d. Game "Chasse aux erreurs" (since contract 1.4)

`POST /engine/sessions/{id}/game` starts 5 rounds. Show `round.problem`, the numbered `round.steps` as clickable
lines and the 3 `round.reasons`; send `POST /engine/sessions/{id}/game/answer {"step": 2, "reason": "B"}`; show
`feedback` and `message`, then the next `round`. Points and streak in the header (hidden with `calm_theme`).

## 6e. Study Studio (real since step 12)

Tool grid → `POST /engine/sessions/{id}/studio {"tool": "flashcards" | "summary" | "quiz" | "slides" | "pdf" |
"diagram", "source": {"kind": "diagnosis"}}`. Always print "Targeted at: …" (`targeted_at`), the sources, and
download links `GET /engine/exports/{session_id}/{file}` (file = last part of `files[].path`). Flashcard review
screen: list `GET /engine/sessions/{id}/cards`, approve / reject with `POST /engine/cards/{card_id}/verify`;
study verified cards with `…/cards?verified_only=true` and `POST /engine/sessions/{id}/cards/{card_id}/review`.

## 7. Other endpoints

`GET /engine/misconceptions` (names FR/AR/EN), `GET /engine/results` and `/engine/results/{name}` (read-only
metrics: show each number with its `script` field), `GET /engine/sessions/{id}/summary` (Report page),
`GET /engine/sessions/{id}` (judge panel: posterior, next question + IG, guard events, cost).
