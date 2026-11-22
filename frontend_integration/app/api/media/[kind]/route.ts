// Thin proxy to the TRACE engine: POST /api/v1/media/image | /api/v1/media/video (a video takes up to ~1 minute,
// longer than the /engine rewrite proxy waits). No LLM call here.
const ENGINE = process.env.TRACE_ENGINE_URL ?? 'http://127.0.0.1:8000/api/v1'

export const maxDuration = 300

export async function POST(req: Request, ctx: { params: Promise<{ kind: string }> }) {
  const { kind } = await ctx.params
  if (kind !== 'image' && kind !== 'video') return Response.json({ detail: 'Unknown media' }, { status: 404 })
  const body = await req.text().catch(() => '')
  const auth = req.headers.get('authorization')
  try {
    const r = await fetch(`${ENGINE}/media/${kind}`, {
      method: 'POST', body, cache: 'no-store', signal: AbortSignal.timeout(280_000),
      headers: { 'Content-Type': 'application/json', ...(auth ? { Authorization: auth } : {}) },
    })
    return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } })
  } catch {
    return Response.json({ detail: 'TRACE engine unreachable or too slow on ' + ENGINE }, { status: 502 })
  }
}
