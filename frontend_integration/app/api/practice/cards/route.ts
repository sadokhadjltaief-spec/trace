// Thin proxy to the TRACE engine: POST /api/v1/practice/cards (multipart). No LLM call here.
import { forwardForm } from '@/lib/engine-proxy'

export const maxDuration = 300

export async function POST(req: Request) {
  return forwardForm(req, '/practice/cards')
}
