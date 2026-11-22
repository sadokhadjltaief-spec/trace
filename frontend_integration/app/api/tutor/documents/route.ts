// Thin proxy to the TRACE engine: POST /api/v1/tutor/documents (a PDF attached in the AI tutor chat, multipart).
const ENGINE = process.env.TRACE_ENGINE_URL ?? 'http://127.0.0.1:8000/api/v1'

export const maxDuration = 120

export async function POST(req: Request) {
  const form = await req.formData().catch(() => null)
  if (!form) return Response.json({ detail: { code: 'doc_not_pdf' } }, { status: 400 })
  const auth = req.headers.get('authorization')
  try {
    const r = await fetch(`${ENGINE}/tutor/documents`, {
      method: 'POST', body: form, cache: 'no-store', signal: AbortSignal.timeout(110_000),
      headers: auth ? { Authorization: auth } : {},
    })
    return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } })
  } catch {
    return Response.json({ detail: { code: 'network' } }, { status: 502 })
  }
}
