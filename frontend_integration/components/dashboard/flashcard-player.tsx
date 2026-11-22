'use client'

// Flashcard player: the card shows the question; a click (or Space / Enter) flips it to the answer.
// "Je savais" / "Je ne savais pas": a missed card comes back at the end of the deck until it is known.
// Cards arrive from the TRACE engine, checked by its guards (generated from the student's material).
import { useEffect, useState } from 'react'
import { ArrowLeft, Check, Layers, RotateCcw, X } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { MathText } from './math-text'
import { cn } from '@/lib/utils'
import type { PracticeCards } from './preparation-experience'

const COPY: Record<Lang, Record<string, string>> = {
  en: { back: 'Back', card: 'Card', of: 'of', flip: 'Click the card to see the answer', question: 'Question', answer: 'Answer', knew: 'I knew it', didnt: 'I did not know', done: 'Deck finished', known: 'known on the first try', again: 'Review the missed cards', restart: 'Start again', left: 'cards left' },
  fr: { back: 'Retour', card: 'Carte', of: 'sur', flip: 'Clique sur la carte pour voir la réponse', question: 'Question', answer: 'Réponse', knew: 'Je savais', didnt: 'Je ne savais pas', done: 'Paquet terminé', known: 'connues du premier coup', again: 'Revoir les cartes manquées', restart: 'Recommencer', left: 'cartes restantes' },
  ar: { back: 'رجوع', card: 'البطاقة', of: 'من', flip: 'انقر على البطاقة لرؤية الإجابة', question: 'السؤال', answer: 'الإجابة', knew: 'كنت أعرف', didnt: 'لم أكن أعرف', done: 'انتهت البطاقات', known: 'عُرفت من المحاولة الأولى', again: 'راجع البطاقات الفائتة', restart: 'ابدأ من جديد', left: 'بطاقات متبقّية' },
}

type Card = PracticeCards['cards'][number]

export function FlashcardPlayer({ deck, lang, onExit }: { deck: PracticeCards; lang: Lang; onExit: () => void }) {
  const c = COPY[lang]
  const all = deck.cards.filter((x) => x.front.shown_allowed && x.back.shown_allowed)
  const [queue, setQueue] = useState<Card[]>(all)
  const [flipped, setFlipped] = useState(false)
  const [firstTry, setFirstTry] = useState<Set<string>>(new Set())
  const [missed, setMissed] = useState<Set<string>>(new Set())
  const [seen, setSeen] = useState(0)
  const card = queue[0]

  function answer(knew: boolean) {
    if (!card) return
    if (knew && !missed.has(card.id)) setFirstTry((s) => new Set(s).add(card.id))
    if (!knew) setMissed((s) => new Set(s).add(card.id))
    setSeen((n) => n + 1)
    setFlipped(false)
    setQueue((q) => (knew ? q.slice(1) : [...q.slice(1), q[0]]))
  }

  function restart(cards: Card[]) {
    setQueue(cards)
    setFlipped(false)
    setFirstTry(new Set())
    setMissed(new Set())
    setSeen(0)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!card) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        setFlipped((f) => !f)
      } else if (flipped && e.key === 'ArrowRight') answer(true)
      else if (flipped && e.key === 'ArrowLeft') answer(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const header = (
    <button type="button" onClick={onExit} className="inline-flex min-h-10 items-center gap-2 self-start rounded-lg px-2 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
      {c.back}
    </button>
  )

  if (!card) {
    const missedCards = all.filter((x) => missed.has(x.id))
    return (
      <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12" aria-labelledby="cards-done">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
          {header}
          <div className="flex flex-col items-center rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
            <span className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-secondary text-primary">
              <Layers className="size-8" aria-hidden="true" />
            </span>
            <h1 id="cards-done" className="text-2xl font-bold text-foreground">{c.done}</h1>
            <p className="mt-2 text-5xl font-bold tabular-nums text-primary">{firstTry.size} / {all.length}</p>
            <p className="mt-1 text-muted-foreground">{c.known}</p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              {missedCards.length ? (
                <button type="button" onClick={() => restart(missedCards)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  {c.again} ({missedCards.length})
                </button>
              ) : null}
              <button type="button" onClick={() => restart(all)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-border px-5 py-2.5 font-semibold text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <RotateCcw className="size-4" aria-hidden="true" />
                {c.restart}
              </button>
            </div>
          </div>
          <p className="text-center text-xs text-muted-foreground">{deck.note}</p>
        </div>
      </section>
    )
  }

  const done = all.length - queue.length
  return (
    <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12" aria-labelledby="card-title">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        {header}
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tabular-nums text-muted-foreground">{queue.length} {c.left}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={all.length} aria-valuenow={done}>
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-brand-cyan transition-[width] duration-300" style={{ width: `${(done / Math.max(all.length, 1)) * 100}%` }} />
          </div>
        </div>

        <div className="[perspective:1200px]">
          <button
            type="button"
            onClick={() => setFlipped((f) => !f)}
            aria-label={flipped ? c.answer : c.question}
            aria-pressed={flipped}
            className="relative block min-h-72 w-full rounded-3xl text-start transition-transform duration-500 [transform-style:preserve-3d] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
            style={{ transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)' }}
          >
            <span className="absolute inset-0 flex flex-col rounded-3xl border border-border bg-card p-6 shadow-sm [backface-visibility:hidden] sm:p-8">
              <span className="text-xs font-semibold uppercase tracking-wide text-primary">{c.question}</span>
              <span id="card-title" className="my-auto py-6 text-center text-xl font-bold leading-snug text-foreground sm:text-2xl"><MathText text={card.front.text} /></span>
              <span className="text-center text-xs text-muted-foreground">{c.flip}</span>
            </span>
            <span className="absolute inset-0 flex flex-col rounded-3xl border border-primary/40 bg-secondary p-6 shadow-sm [backface-visibility:hidden] [transform:rotateY(180deg)] sm:p-8">
              <span className="text-xs font-semibold uppercase tracking-wide text-primary-deep">{c.answer}</span>
              <span className="my-auto py-6 text-center text-lg leading-relaxed text-foreground"><MathText text={card.back.text} /></span>
            </span>
          </button>
        </div>

        <div className={cn('grid grid-cols-2 gap-3 transition-opacity', flipped ? 'opacity-100' : 'pointer-events-none opacity-40')} aria-hidden={!flipped}>
          <button type="button" disabled={!flipped} onClick={() => answer(false)} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 font-semibold text-destructive transition hover:bg-destructive/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed">
            <X className="size-4" aria-hidden="true" />
            {c.didnt}
          </button>
          <button type="button" disabled={!flipped} onClick={() => answer(true)} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed">
            <Check className="size-4" aria-hidden="true" />
            {c.knew}
          </button>
        </div>
        <p className="text-center text-xs text-muted-foreground">{c.card} {Math.min(seen + 1, seen + queue.length)} · {deck.note}</p>
      </div>
    </section>
  )
}
