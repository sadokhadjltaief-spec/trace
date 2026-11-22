// Thin proxy to the TRACE engine: POST /api/v1/textbooks (building a textbook takes up to ~2 minutes on the free tier).
const ENGINE = process.env.TRACE_ENGINE_URL ?? 'http://127.0.0.1:8000/api/v1'

export const maxDuration = 300

export async function POST(req: Request) {
  const body = await req.text().catch(() => '')
  const auth = req.headers.get('authorization')
  try {
    const r = await fetch(`${ENGINE}/textbooks`, {
      method: 'POST', body, cache: 'no-store', signal: AbortSignal.timeout(290_000),
      headers: { 'Content-Type': 'application/json', ...(auth ? { Authorization: auth } : {}) },
    })
    return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } })
  } catch {
    return Response.json({ detail: 'TRACE engine unreachable or too slow on ' + ENGINE }, { status: 502 })
  }
}
