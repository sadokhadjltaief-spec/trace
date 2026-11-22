// Server-side proxy to the TRACE engine (FastAPI) for long calls (quiz, flashcards, summary, study plan).
// The /engine/* rewrite is fine for short calls, but its proxy times out on generations that take ~1 minute
// (the first time a file is used); a route handler waits as long as needed.

const ENGINE = process.env.TRACE_ENGINE_URL ?? 'http://127.0.0.1:8000/api/v1'

export async function forwardForm(req: Request, path: string): Promise<Response> {
  const form = await req.formData().catch(() => null)
  if (!form) return Response.json({ detail: 'Invalid request' }, { status: 400 })
  try {
    const r = await fetch(`${ENGINE}${path}`, { method: 'POST', body: form, cache: 'no-store', signal: AbortSignal.timeout(280_000) })
    return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } })
  } catch {
    return Response.json({ detail: 'TRACE engine unreachable or too slow on ' + ENGINE }, { status: 502 })
  }
}
