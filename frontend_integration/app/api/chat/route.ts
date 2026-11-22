// Thin proxy to the TRACE engine (FastAPI, C:\TRACE\server\main.py). No LLM call, no prompt, no text generated
// here: the engine decides every message and checks it with its guards before it is returned.
// The previous direct LLM call (streamText) is kept in _backup_avant_trace/app/api/chat/route.ts.

const ENGINE = process.env.TRACE_ENGINE_URL ?? 'http://127.0.0.1:8000/api/v1'

type Action =
  | {
      action: 'start'
      student: { name: string; level: string; lang: 'fr' | 'ar' | 'en' }
      profile?: Record<string, unknown>
      demo?: boolean
    }
  | {
      action: 'answer'
      sessionId: string
      question_id: string
      option: string
      confidence: 'sure' | 'unsure'
      explanation?: string | null
    }
  | { action: 'reply'; sessionId: string; choice?: string | null; text?: string | null }
  | { action: 'state' | 'summary'; sessionId: string }
  | { action: 'ask'; question: string; lang: 'fr' | 'ar' | 'en'; sessionId?: string | null }

export async function POST(req: Request) {
  const b = (await req.json().catch(() => null)) as Action | null
  if (!b || typeof b !== 'object' || !('action' in b)) {
    return Response.json({ detail: 'Invalid request' }, { status: 400 })
  }
  const sid = 'sessionId' in b && b.sessionId ? encodeURIComponent(b.sessionId) : ''
  const call = (path: string, body?: unknown) =>
    fetch(`${ENGINE}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    })
  let r: Response
  try {
    switch (b.action) {
      case 'start':
        r = await call('/sessions', { student: b.student, profile: b.profile ?? {}, demo: b.demo ?? true })
        break
      case 'answer':
        r = await call(`/sessions/${sid}/answer`, {
          question_id: b.question_id,
          option: b.option,
          confidence: b.confidence,
          explanation: b.explanation ?? null,
        })
        break
      case 'reply':
        r = await call(`/sessions/${sid}/reply`, { choice: b.choice ?? null, text: b.text ?? null })
        break
      case 'state':
        r = await call(`/sessions/${sid}`)
        break
      case 'summary':
        r = await call(`/sessions/${sid}/summary`)
        break
      case 'ask': // course chat: answers from the course files with citations, off-topic refused by the engine
        r = await call('/chat', { question: b.question, lang: b.lang, session_id: b.sessionId ?? null })
        break
      default:
        return Response.json({ detail: 'Unknown action' }, { status: 400 })
    }
  } catch {
    return Response.json({ detail: 'TRACE engine unreachable on ' + ENGINE }, { status: 502 })
  }
  return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } })
}
