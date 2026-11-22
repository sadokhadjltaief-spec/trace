'use client'

// Readable view of one page of the student's own PDF (text extracted by the TRACE engine). PDF text extraction cuts
// formulas into one symbol per line and loses some glyphs (big brackets, integral signs). This view only re-arranges
// that text: lines are joined into paragraphs, formula fragments are grouped into one formula box, unreadable glyphs
// are dropped, short title lines become headings. No word is invented.
import { Fragment } from 'react'
import { MathText } from './math-text'

type Block = { kind: 'h' | 'p' | 'li' | 'formula'; text: string }

// private-use / replacement / box glyphs = PDF symbols the extractor could not map
const JUNK = /[-�□▯☐\u0000-\u0008\u000B\u000C\u000E-\u001F]/g
const BULLET = /^\s*(?:[•▪◦●○■□➢➤►\-–*]|o\s|\d{1,2}[.)]\s)\s*/
const MATHY = /[=∂∫∑√≤≥≈±×÷→⇒⇓⇔∞πΔλμσθαβγ^_]|^\(?[A-Za-z]{1,3}\d?\)?$|^[\d\s.,+\-*/()[\]{}|]+$/

function words(s: string) {
  return (s.match(/[A-Za-zÀ-ÿ؀-ۿ]{2,}/g) ?? []).length
}

function isFormulaPiece(line: string) {
  if (words(line) >= 4 && !/[=∂∫]/.test(line)) return false
  // plain words without any maths sign or digit ("M SAHRAOUI", "Premier Principe") are text, not formula pieces
  if (/[A-Za-zÀ-ÿ؀-ۿ]{3,}/.test(line) && !/[\d=∂∫∑√()[\]^_+\-*/<>≤≥]/.test(line)) return false
  return line.length <= 18 || MATHY.test(line)
}

export function pageBlocks(raw: string): Block[] {
  // TeX big brackets come out as control characters: \x12 = (, \x13 = ), \x14 = [, \x15 = ]
  const fixed = raw.replace(/\x12/g, '(').replace(/\x13/g, ')').replace(/\x14/g, '[').replace(/\x15/g, ']')
  const lines = fixed.replace(JUNK, '').split(/\r?\n/).map((l) => l.replace(/\s+/g, ' ').trim()).filter(Boolean)
    .filter((l) => !/^\d{1,3}\s*\/\s*\d{1,3}$/.test(l) && !/^\d{1,2}\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}$/i.test(l))
  // drop a line repeated right after itself (headers extracted twice)
  const uniq = lines.filter((l, i) => i === 0 || l.toLowerCase() !== lines[i - 1].toLowerCase())
  const out: Block[] = []
  let formula: string[] = []
  const flushFormula = () => {
    if (!formula.length) return
    const text = formula.join(' ').replace(/\s+([)\]},.])/g, '$1').replace(/([([{])\s+/g, '$1').trim()
    if (text) out.push({ kind: 'formula', text })
    formula = []
  }
  for (let i = 0; i < uniq.length; i++) {
    let line = uniq[i]
    const next = uniq[i + 1] ?? ''
    if (line === '⇓' || line === '⇒') { flushFormula(); continue }
    if (isFormulaPiece(line) && (formula.length || isFormulaPiece(next) || /[=∂∫]/.test(line))) {
      if (/^Z(\s|$)/.test(line)) line = line.replace(/^Z/, '∫') // integral sign extracted as "Z"
      // a new equation ("Cp(T) =") starts a new formula box
      if (/=\s*$/.test(line) && formula.some((f) => f.includes('='))) flushFormula()
      formula.push(line)
      continue
    }
    flushFormula()
    if (BULLET.test(line)) { out.push({ kind: 'li', text: line.replace(BULLET, '') }); continue }
    const looksTitle = words(line) <= 8 && !/[.;:,?!]$/.test(line) && /^[A-ZÀ-Ý0-9؀-ۿ]/.test(line) && line.length < 70
    if (looksTitle && (!next || /^[A-ZÀ-Ý؀-ۿ]/.test(next) || isFormulaPiece(next))) {
      out.push({ kind: 'h', text: line })
      continue
    }
    const prev = out[out.length - 1]
    if (prev && prev.kind === 'p' && !/[.:;?!]$/.test(prev.text)) prev.text += ' ' + line
    else out.push({ kind: 'p', text: line })
  }
  flushFormula()
  // a heading repeated as the next heading (slide title + subtitle) is kept once
  return out.filter((b, i) => !(b.kind === 'h' && out[i - 1]?.kind === 'h' && out[i - 1].text.toLowerCase() === b.text.toLowerCase()))
}

export function PageText({ text, dir }: { text: string; dir?: 'rtl' | 'ltr' }) {
  const blocks = pageBlocks(text)
  return (
    <div className="flex flex-col gap-3 text-pretty text-base leading-relaxed text-foreground" dir={dir}>
      {blocks.map((b, k) => (
        <Fragment key={k}>
          {b.kind === 'h' ? (
            <h3 className="mt-2 flex items-center gap-2 text-lg font-bold text-foreground first:mt-0">
              <span className="h-5 w-1 shrink-0 rounded-full bg-primary" aria-hidden="true" />{b.text}
            </h3>
          ) : b.kind === 'formula' ? (
            <div className="overflow-x-auto rounded-2xl border border-primary/20 bg-secondary/40 px-4 py-3 text-center text-[1.05rem] font-medium tracking-wide text-foreground" dir="ltr">
              {b.text}
            </div>
          ) : b.kind === 'li' ? (
            <p className="flex gap-2.5 ps-1"><span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-primary" aria-hidden="true" /><span><MathText text={b.text} /></span></p>
          ) : (
            <p><MathText text={b.text} /></p>
          )}
        </Fragment>
      ))}
    </div>
  )
}
