// Thin proxy: forwards the uploaded files to the TRACE engine (FastAPI) which builds the study plan.
// No LLM call here: the engine reads the pages, writes the plan (cached), and checks every text with its guards.

const ENGINE = process.env.TRACE_ENGINE_URL ?? 'http://127.0.0.1:8000/api/v1'

export async function POST(req: Request) {
  const form = await req.formData().catch(() => null)
  if (!form || form.getAll('files').length === 0) {
    return Response.json({ detail: 'No file' }, { status: 400 })
  }
  try {
    const r = await fetch(`${ENGINE}/study-plan`, { method: 'POST', body: form, cache: 'no-store' })
    return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } })
  } catch {
    return Response.json({ detail: 'TRACE engine unreachable on ' + ENGINE }, { status: 502 })
  }
}
