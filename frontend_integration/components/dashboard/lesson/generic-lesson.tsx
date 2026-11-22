'use client'

// The same interactive lesson layout for ANY attached PDF or tutor explanation (no fractions content is ever shown for
// another subject). The content is the engine's checked "textbook" (POST /api/v1/textbooks): every text passed the
// guards, every prediction question was cross-checked blind and its answer key stays on the server (revealed after the
// student chose). Three.js is used only when the engine picked a geometric solid (box, cylinder, cone, sphere,
// pyramid, prism); other visuals are the engine's computed diagrams.
import { useCallback, useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { motion } from 'motion/react'
import { Award, BookOpen, Check, CircleHelp, Eye, Lightbulb, LoaderCircle, Sparkles, Target } from 'lucide-react'
import { authHeader } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { MathText } from '../math-text'
import { webglOk } from './fraction-cake-3d'

const Solid3D = dynamic(() => import('./solid-3d').then((m) => m.Solid3D), { ssr: false, loading: () => null })
const SOLIDS = new Set(['box', 'cylinder', 'cone', 'sphere', 'pyramid', 'prism'])

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
type Book = { textbook_id: string; title: string; spreads: Spread[]; completed: number }

const T = {
  fr: { building: 'Je construis ta leçon interactive…', hint: 'Le moteur lit le document, vérifie chaque texte et chaque question. Cela peut prendre une à deux minutes.', error: 'La leçon n’a pas pu être construite.', objectives: 'Objectifs', predict: 'Prédis avant de voir', why: 'Pourquoi ?', vocab: 'Vocabulaire', tap: 'touche un mot', visual: 'Observer', summary: 'Résumé', done: 'Leçon terminée', of: 'sur', page: 'p.', drag: 'Fais tourner le solide', right: 'Bonne prédiction.', wrong: 'Pas tout à fait.' },
  en: { building: 'Building your interactive lesson…', hint: 'The engine reads the document and checks every text and question. It can take one or two minutes.', error: 'The lesson could not be built.', objectives: 'Objectives', predict: 'Predict before you look', why: 'Why?', vocab: 'Vocabulary', tap: 'tap a word', visual: 'Observe', summary: 'Summary', done: 'Lesson finished', of: 'of', page: 'p.', drag: 'Rotate the solid', right: 'Good prediction.', wrong: 'Not quite.' },
  ar: { building: 'أبني درسك التفاعلي…', hint: 'يقرأ المحرك الوثيقة ويتحقق من كل نص وسؤال. قد يستغرق ذلك دقيقة أو دقيقتين.', error: 'تعذّر بناء الدرس.', objectives: 'الأهداف', predict: 'توقّع قبل أن ترى', why: 'لماذا؟', vocab: 'المفردات', tap: 'المس كلمة', visual: 'لاحظ', summary: 'الملخص', done: 'انتهى الدرس', of: 'من', page: 'ص', drag: 'أدر المجسم', right: 'توقع صحيح.', wrong: 'ليس تمامًا.' },
}
export type GenericCopy = typeof T.fr

function Lesson({ s, i, c, onAnswer, onEvent }: { s: Spread; i: number; c: GenericCopy; onAnswer: (choice: number) => Promise<void>; onEvent: (e: 'vocab' | 'visual') => void }) {
  const [open, setOpen] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [gl, setGl] = useState(false)
  useEffect(() => setGl(webglOk()), [])
  const p = s.prediction
  const answered = p.choice !== undefined && p.choice !== null
  const solid = SOLIDS.has(s.model3d?.kind) && gl
  return (
    <motion.section id={`lesson-s${i}`} className="scroll-mt-28" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-80px' }}>
      <div className="mb-4 flex items-center gap-3">
        <span className={cn('flex size-10 items-center justify-center rounded-2xl text-lg font-extrabold', s.completed ? 'bg-emerald-500 text-white' : 'bg-primary text-primary-foreground')}>{s.completed ? <Check className="size-5" /> : i + 1}</span>
        <h2 className="text-2xl font-bold tracking-tight text-foreground"><MathText text={s.title} /></h2>
        {s.pages?.length ? <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-bold text-primary-deep">{c.page} {s.pages.join(', ')}</span> : null}
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
        <div className="flex flex-col gap-4 rounded-3xl border border-border bg-card p-6 shadow-sm">
          <p className="text-lg leading-relaxed text-foreground"><MathText text={s.concept} /></p>
          {s.key ? (
            <div className="rounded-2xl bg-gradient-to-br from-primary/10 to-brand-cyan/10 p-4">
              <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-primary"><Lightbulb className="size-4" />{s.key_label}</p>
              <p className="mt-2 text-center text-xl font-semibold text-foreground"><MathText text={s.key} formula /></p>
            </div>
          ) : null}
          {s.vocab.length ? (
            <div>
              <p className="text-sm font-bold text-foreground">{c.vocab} <span className="font-normal text-muted-foreground">· {c.tap}</span></p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {s.vocab.map((v, k) => (
                  <button key={k} type="button" onClick={() => { const n = new Set(open).add(k); setOpen(n); if (n.size === s.vocab.length) onEvent('vocab') }}
                    className={cn('rounded-2xl border p-3 text-start text-sm transition', open.has(k) ? 'border-primary/40 bg-secondary/60' : 'border-border bg-background hover:border-primary/50')}>
                    <span className="font-bold text-foreground">{v.term}</span>
                    {open.has(k) ? <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-1 block text-muted-foreground"><MathText text={v.definition} /></motion.span> : <Eye className="ms-2 inline size-3.5 text-muted-foreground" />}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div className="flex flex-col gap-4">
          <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-primary"><CircleHelp className="size-4" />{c.predict}</p>
            <p className="mt-2 font-semibold text-foreground"><MathText text={p.question} /></p>
            <div className="mt-3 flex flex-col gap-2">
              {p.options.map((o, k) => (
                <button key={k} type="button" disabled={answered || busy} onClick={async () => { setBusy(true); try { await onAnswer(k) } finally { setBusy(false) } }}
                  className={cn('rounded-xl border px-3 py-2.5 text-start text-sm transition', !answered ? 'border-border bg-background hover:border-primary/50' : k === p.correct_index ? 'border-emerald-500 bg-emerald-500/12' : k === p.choice ? 'border-rose-500 bg-rose-500/12' : 'border-border opacity-60')}>
                  <MathText text={o} />
                </button>
              ))}
            </div>
            {answered ? (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={cn('mt-3 rounded-2xl p-3 text-sm', p.was_correct ? 'bg-emerald-500/12' : 'bg-rose-500/12')}>
                <p className="font-bold">{p.was_correct ? c.right : c.wrong} {c.why}</p>
                <p className="mt-1 text-foreground"><MathText text={p.why ?? ''} /></p>
              </motion.div>
            ) : null}
          </div>
          {solid ? (
            <div onPointerDown={() => onEvent('visual')}>
              <Solid3D kind={s.model3d.kind} params={s.model3d.params} label={s.model3d.label || s.title} />
              <p className="mt-1 text-xs text-muted-foreground">{c.drag}{s.model3d.label ? ` · ${s.model3d.label}` : ''}</p>
            </div>
          ) : s.image ? (
            <figure className="overflow-hidden rounded-3xl border border-border bg-white p-3" onMouseEnter={() => onEvent('visual')} onClick={() => onEvent('visual')}>
              <img src={s.image.url} alt={s.image.title} className="w-full" />
              {s.image.caption ? <figcaption className="mt-2 text-sm text-neutral-700"><MathText text={s.image.caption} /></figcaption> : null}
            </figure>
          ) : null}
        </div>
      </div>
    </motion.section>
  )
}

export function GenericLesson({ lang, source, onProgress }: { lang: 'fr' | 'en' | 'ar'; source: { docId?: string; text?: string }; onProgress: (title: string, sections: { id: string; letter: string; title: string }[], done: number, total: number) => void }) {
  const c = T[lang] ?? T.fr
  const [book, setBook] = useState<Book | null>(null)
  const [error, setError] = useState('')
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    fetch('/api/textbooks', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify({ lang, doc_id: source.docId ?? null, text: source.docId ? null : source.text ?? null }) })
      .then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : `HTTP ${r.status}`); return d as Book })
      .then(setBook)
      .catch((e: Error) => setError(`${c.error} (${e.message})`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!book) return
    onProgress(book.title, [{ id: 'intro', letter: 'A', title: c.objectives }, ...book.spreads.map((s, i) => ({ id: `s${i}`, letter: String(i + 1), title: s.title })), { id: 'summary', letter: '✓', title: c.summary }],
      book.spreads.filter((s) => s.completed).length, book.spreads.length)
  }, [book, onProgress, c])

  const patch = useCallback((i: number, upd: Partial<Spread>) => setBook((b) => (b ? { ...b, spreads: b.spreads.map((s, k) => (k === i ? { ...s, ...upd } : s)) } : b)), [])
  async function call<R>(i: number, path: string, body: unknown): Promise<R> {
    const r = await fetch(`/engine/textbooks/${book!.textbook_id}/spreads/${i}/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify(body) })
    const d = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : `HTTP ${r.status}`)
    return d as R
  }

  if (error) return <div className="m-6 rounded-2xl bg-destructive/10 p-5 text-destructive" role="alert">{error}</div>
  if (!book) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-8 text-center">
        <LoaderCircle className="size-10 animate-spin text-primary motion-reduce:animate-none" />
        <p className="text-xl font-semibold text-foreground">{c.building}</p>
        <p className="max-w-md text-sm text-muted-foreground">{c.hint}</p>
      </div>
    )
  }
  const completed = book.spreads.filter((s) => s.completed).length
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-14 px-4 pb-24 pt-8 md:px-8" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      <header id="lesson-intro" className="relative scroll-mt-28 overflow-hidden rounded-[2rem] border border-border bg-gradient-to-br from-primary/15 via-card to-brand-cyan/15 p-7 sm:p-10">
        <p className="inline-flex items-center gap-2 rounded-full bg-background/80 px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-primary-deep"><Sparkles className="size-4" />{c.objectives}</p>
        <h1 className="mt-4 text-balance text-4xl font-bold tracking-tight text-foreground sm:text-5xl"><MathText text={book.title} /></h1>
        <ul className="mt-5 grid gap-2 sm:grid-cols-2">
          {book.spreads.map((s, i) => <li key={i} className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm font-semibold text-foreground"><Target className="size-4 shrink-0 text-primary" /><MathText text={s.title} /></li>)}
        </ul>
      </header>
      {book.spreads.map((s, i) => (
        <Lesson key={i} s={s} i={i} c={c}
          onAnswer={async (choice) => {
            const r = await call<{ correct: boolean; correct_index: number; why: string; events: string[]; completed: boolean }>(i, 'answer', { choice })
            patch(i, { prediction: { ...s.prediction, choice, correct_index: r.correct_index, why: r.why, was_correct: r.correct }, events: r.events, completed: r.completed })
            const f = await call<{ events: string[]; completed: boolean }>(i, 'event', { event: 'flap' }).catch(() => null)
            if (f) patch(i, { events: f.events, completed: f.completed })
          }}
          onEvent={async (e) => {
            if (s.events.includes(e)) return
            const r = await call<{ events: string[]; completed: boolean }>(i, 'event', { event: e }).catch(() => null)
            if (r) patch(i, { events: r.events, completed: r.completed })
          }} />
      ))}
      <section id="lesson-summary" className="scroll-mt-28 rounded-3xl border border-border bg-gradient-to-br from-emerald-500/10 via-card to-primary/10 p-6 sm:p-8">
        <h2 className="flex items-center gap-2 text-2xl font-bold text-foreground"><BookOpen className="size-6 text-primary" />{c.summary}</h2>
        <ul className="mt-4 grid gap-3 md:grid-cols-2">
          {book.spreads.filter((s) => s.key).map((s, i) => <li key={i} className="rounded-2xl bg-background/80 p-4"><p className="text-sm font-bold text-foreground"><MathText text={s.title} /></p><p className="mt-1 text-foreground"><MathText text={s.key} formula /></p></li>)}
        </ul>
        <p className="mt-5 flex items-center gap-3 font-bold text-foreground"><Award className={cn('size-8', completed === book.spreads.length ? 'text-primary' : 'text-muted-foreground')} />{completed} {c.of} {book.spreads.length}{completed === book.spreads.length ? ` · ${c.done}` : ''}</p>
      </section>
    </div>
  )
}
