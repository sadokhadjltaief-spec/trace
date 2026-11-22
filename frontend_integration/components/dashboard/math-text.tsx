'use client'

// Renders maths inside generated text with KaTeX. The TRACE engine writes maths as plain text ("2/3 × 5 = 10/3");
// this finds the maths parts (numbers joined by operators or "=") and typesets them: a/b becomes a real fraction,
// × and · stay as signs. Explicit $...$ or \(...\) segments are rendered as TeX. Everything else stays plain text.
// `formula`: the whole text is one formula ("a/b + c/d = (ad+bc)/bd"), letters allowed, if it contains no word.
import katex from 'katex'
import 'katex/dist/katex.min.css'
import { useMemo } from 'react'

const TEX = /\$([^$]+)\$|\\\((.+?)\\\)/g
// a run of numbers / parentheses joined by operators; it must contain an operator to count as maths
const PLAIN = /[(−-]*\d[\d\s+\-−*/×÷·=().,^]*[\d)]/g
const HAS_OP = /[+\-−*/×÷·=^]/
const WORD = /[A-Za-zÀ-ÿ]{3,}/

function signs(tex: string): string {
  return tex
    .replace(/×|\*/g, '\\times ')
    .replace(/÷/g, '\\div ')
    .replace(/·/g, '\\cdot ')
    .replace(/≠/g, '\\neq ')
}

function toTex(expr: string): string {
  const t = expr
    .trim()
    .replace(/−/g, '-')
    .replace(/(\(?-?\d+(?:[.,]\d+)?\)?)\s*\/\s*(\(?-?\d+(?:[.,]\d+)?\)?)/g, '\\dfrac{$1}{$2}')
    .replace(/,/g, '{,}')
  return signs(t)
}

const unwrap = (s: string) => (s.startsWith('(') && s.endsWith(')') ? s.slice(1, -1) : s)

function formulaTex(expr: string): string {
  const t = expr
    .trim()
    .replace(/−/g, '-')
    .replace(/([A-Za-z0-9]+|\([^()]*\))\s*\/\s*([A-Za-z0-9]+|\([^()]*\))/g, (_m, a: string, b: string) => '\\dfrac{' + unwrap(a) + '}{' + unwrap(b) + '}')
  return signs(t)
}

function render(tex: string): string {
  return katex.renderToString(tex, { throwOnError: false, output: 'html' })
}

type Part = { math: boolean; html?: string; text?: string }

function split(text: string): Part[] {
  const out: Part[] = []
  // 1) explicit TeX
  let last = 0
  const chunks: { s: string; tex?: string }[] = []
  for (const m of text.matchAll(TEX)) {
    if (m.index! > last) chunks.push({ s: text.slice(last, m.index) })
    chunks.push({ s: m[0], tex: m[1] ?? m[2] })
    last = m.index! + m[0].length
  }
  if (last < text.length) chunks.push({ s: text.slice(last) })
  // 2) plain-text maths inside the other chunks
  for (const c of chunks) {
    if (c.tex !== undefined) { out.push({ math: true, html: render(c.tex) }); continue }
    let i = 0
    for (const m of c.s.matchAll(PLAIN)) {
      const raw = m[0]
      if (!HAS_OP.test(raw.replace(/^[(−-]+/, ''))) continue // a lone number ("p.1", "15") stays text
      if (m.index! > i) out.push({ math: false, text: c.s.slice(i, m.index) })
      const lead = raw.match(/^\s*/)?.[0] ?? ''
      const trail = raw.match(/\s*$/)?.[0] ?? ''
      if (lead) out.push({ math: false, text: lead })
      out.push({ math: true, html: render(toTex(raw)) })
      if (trail) out.push({ math: false, text: trail })
      i = m.index! + raw.length
    }
    if (i < c.s.length) out.push({ math: false, text: c.s.slice(i) })
  }
  return out
}

export function MathText({ text, className, formula = false }: { text: string; className?: string; formula?: boolean }) {
  const parts = useMemo<Part[]>(
    () => (formula && !WORD.test(text) && !text.includes('$') ? [{ math: true, html: render(formulaTex(text)) }] : split(text)),
    [text, formula],
  )
  return (
    <span className={className}>
      {parts.map((p, k) =>
        p.math ? <span key={k} dir="ltr" className="inline-block align-middle" dangerouslySetInnerHTML={{ __html: p.html! }} /> : <span key={k}>{p.text}</span>,
      )}
    </span>
  )
}
