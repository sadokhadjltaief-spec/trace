'use client'

// The two pages of a textbook spread, as plain DOM (used on the 3D book through drei <Html transform> and in the 2D
// fallback). Left: lesson (title, concept, key box, vocabulary, prediction question, lift-the-flap "Why?").
// Right: the computed diagram, the 3D model area, the completion stamp. Answer keys come from the engine only after
// the student chose (POST .../answer).
import { useState } from 'react'
import { Check, Eye, Lightbulb, Lock, MousePointerClick, RotateCw, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MathText } from '../math-text'

export type Spread = {
  title: string
  concept: string
  key_label: string
  key: string
  vocab: { term: string; definition: string }[]
  model3d: { kind: string; label: string; params: Record<string, unknown> }
  pages: number[]
  image: { url: string; title: string; caption: string; kind: string } | null
  prediction: { question: string; options: string[]; choice?: number; correct_index?: number; why?: string; was_correct?: boolean }
  events: string[]
  completed: boolean
}

export type BookCopy = Record<string, string>

export const SERIF = "'Newsreader', 'Instrument Serif', 'Playfair Display', 'Iowan Old Style', 'Palatino Linotype', Georgia, serif"

export function LeftPage({ spread, copy, onAnswer, onVocab, number }: {
  spread: Spread; copy: BookCopy; number: number
  onAnswer: (i: number) => Promise<void>; onVocab: () => void
}) {
  const [opened, setOpened] = useState<Set<number>>(() => new Set(spread.events.includes('vocab') ? spread.vocab.map((_, i) => i) : []))
  const [busy, setBusy] = useState(false)
  const p = spread.prediction
  const answered = p.choice !== undefined && p.choice !== null
  const reveal = (i: number) => {
    const n = new Set(opened); n.add(i); setOpened(n)
    if (n.size === spread.vocab.length && !spread.events.includes('vocab')) onVocab()
  }
  return (
    <div className="flex h-full flex-col gap-3 text-[#2b2520]" style={{ fontFamily: SERIF }}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-[#9a6b2f]" style={{ fontFamily: 'inherit' }}>{copy.lesson} {number}</p>
      <h2 className="text-[26px] font-semibold leading-tight">{spread.title}</h2>
      <p className="text-[15px] leading-relaxed"><MathText text={spread.concept} /></p>
      <div className="rounded-lg border-2 border-[#2b2520]/80 bg-[#fff8e6] px-4 py-2.5 shadow-[3px_3px_0_rgba(43,37,32,0.25)]">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#9a6b2f]">{spread.key_label || copy.key}</p>
        <p className="text-[16px] font-medium leading-snug" dir="ltr"><MathText text={spread.key} formula /></p>
      </div>
      <div>
        <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#9a6b2f]">{copy.vocab} <span className="normal-case tracking-normal text-[#2b2520]/60">· {copy.tapTerms}</span></p>
        <ul className="grid gap-1">
          {spread.vocab.map((v, i) => (
            <li key={v.term}>
              <button type="button" onClick={() => reveal(i)} className="w-full rounded-md border border-dashed border-[#2b2520]/30 px-2 py-1 text-start text-[13px] leading-snug hover:bg-[#fff3d1]">
                <b>{v.term}</b>{opened.has(i) ? <span> — {v.definition}</span> : <span className="ms-1 inline-flex items-center gap-1 text-[#2b2520]/50"><Eye className="size-3" />{copy.show}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="mt-auto rounded-lg bg-[#efe6d2] p-3">
        <p className="flex items-center gap-1.5 text-[13px] font-bold"><Lightbulb className="size-4 text-[#c27b1a]" />{copy.predict}</p>
        <p className="mt-1 text-[14px] leading-snug"><MathText text={p.question} /></p>
        <div className="mt-2 grid gap-1.5">
          {p.options.map((o, i) => {
            const isChoice = answered && p.choice === i
            const isRight = answered && p.correct_index === i
            return (
              <button key={i} type="button" disabled={answered || busy}
                onClick={async () => { setBusy(true); try { await onAnswer(i) } finally { setBusy(false) } }}
                className={cn('flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-start text-[13px] leading-snug transition',
                  !answered && 'border-[#2b2520]/25 bg-white hover:border-[#c27b1a] hover:bg-[#fff8e6]',
                  isRight && 'border-emerald-600 bg-emerald-50', isChoice && !isRight && 'border-red-500 bg-red-50',
                  answered && !isRight && !isChoice && 'border-transparent opacity-60')}>
                <span className="font-bold">{String.fromCharCode(65 + i)}.</span><span><MathText text={o} /></span>
              </button>
            )
          })}
        </div>
        {/* lift-the-flap: locked until a choice is made, then it swings open on its top hinge */}
        <div className="relative mt-3 [perspective:700px]">
          <div className={cn('rounded-md border border-[#2b2520]/20 bg-white/80 p-2.5 text-[13px] leading-snug', !answered && 'invisible')}>
            {answered ? (
              <>
                <p className={cn('font-bold', p.was_correct ? 'text-emerald-700' : 'text-red-600')}>
                  {p.was_correct ? copy.right : copy.wrong} {copy.answerIs} {String.fromCharCode(65 + (p.correct_index ?? 0))}
                </p>
                <p className="mt-1"><MathText text={p.why ?? ''} /></p>
              </>
            ) : <p>&nbsp;</p>}
          </div>
          <div aria-hidden={answered}
            className="absolute inset-0 flex origin-top items-center justify-center gap-2 rounded-md border border-[#c9b48a] bg-[repeating-linear-gradient(135deg,#f3e2b8_0_8px,#ecd7a6_8px_16px)] text-[13px] font-bold text-[#6b4d1f] shadow-md transition-transform duration-700 ease-out"
            style={{ transform: answered ? 'rotateX(-172deg)' : 'rotateX(0deg)', backfaceVisibility: 'hidden' }}>
            {answered ? null : <><Lock className="size-3.5" />{copy.flap}</>}
          </div>
        </div>
      </div>
    </div>
  )
}

export function RightPage({ spread, copy, onVisual, has3d, children }: {
  spread: Spread; copy: BookCopy; onVisual: () => void; has3d: boolean; children?: React.ReactNode
}) {
  const done = spread.completed
  const need = [
    { k: 'answered', label: copy.reqAnswer }, { k: 'flap', label: copy.reqFlap },
    { k: 'vocab', label: copy.reqVocab }, { k: 'visual', label: copy.reqVisual },
  ]
  return (
    <div className="relative flex h-full flex-col gap-3 text-[#2b2520]" style={{ fontFamily: SERIF }}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.25em] text-[#9a6b2f]">{copy.visual}</p>
      {spread.image ? (
        <button type="button" onClick={onVisual} className="group relative overflow-hidden rounded-md border-2 border-[#2b2520]/70 bg-white shadow-[3px_3px_0_rgba(43,37,32,0.25)]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={spread.image.url} alt={spread.image.title} className="w-full mix-blend-multiply [filter:grayscale(0.15)_contrast(1.05)]" />
          <span className="absolute end-2 top-2 inline-flex items-center gap-1 rounded-full bg-[#2b2520]/80 px-2 py-0.5 text-[11px] text-white opacity-0 transition group-hover:opacity-100"><MousePointerClick className="size-3" />{copy.explore}</span>
        </button>
      ) : null}
      {spread.image?.caption ? <p className="text-[13px] italic leading-snug text-[#2b2520]/80"><MathText text={spread.image.caption} /></p> : null}
      {has3d ? (
        <div className="pointer-events-none relative min-h-[150px] flex-1 rounded-md border border-dashed border-[#2b2520]/35">
          <span className="absolute start-2 top-1.5 inline-flex items-center gap-1 text-[11px] text-[#2b2520]/60"><RotateCw className="size-3" />{copy.rotate} · {spread.model3d.label}</span>
          {children}
        </div>
      ) : !spread.image ? (
        <button type="button" onClick={onVisual} className="flex flex-1 items-center justify-center rounded-md border border-dashed border-[#2b2520]/35 text-[13px]">{copy.noVisual}</button>
      ) : <div className="flex-1" />}
      <div className="flex items-end justify-between gap-3">
        <ul className="grid gap-0.5 text-[12px]">
          {need.map((n) => (
            <li key={n.k} className={cn('flex items-center gap-1.5', spread.events.includes(n.k) ? 'text-emerald-700' : 'text-[#2b2520]/55')}>
              <span className={cn('flex size-3.5 items-center justify-center rounded-full border', spread.events.includes(n.k) ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-[#2b2520]/40')}>{spread.events.includes(n.k) ? <Check className="size-2.5" /> : null}</span>
              {n.label}
            </li>
          ))}
        </ul>
        {/* completion stamp: dashed circle that becomes an inked stamp only after every required interaction */}
        <div className="relative flex size-24 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-[#2b2520]/35">
          {done ? (
            <div className="wasla-stamp flex size-[5.6rem] -rotate-12 flex-col items-center justify-center rounded-full border-4 border-[#b4232c] text-center text-[#b4232c]">
              <Sparkles className="size-4" />
              <span className="text-[11px] font-black uppercase leading-tight tracking-wider">{copy.stamp}</span>
            </div>
          ) : <span className="px-2 text-center text-[10px] leading-tight text-[#2b2520]/45">{copy.stampHint}</span>}
        </div>
      </div>
      {spread.pages.length ? <p className="text-[11px] text-[#2b2520]/50">{copy.source} {spread.pages.join(', ')}</p> : null}
    </div>
  )
}
