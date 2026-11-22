'use client'

// Interactive textbook: built by the TRACE engine from a PDF attached in the chat or from a tutor explanation
// (POST /api/v1/textbooks). 3D book (React Three Fiber) on desktop with WebGL; a flat 2D book on small screens or
// without WebGL (same pages, same interactions). Progress (answers, flap, vocabulary, visual, stamp) is saved by the
// engine for the signed-in student.
import dynamic from 'next/dynamic'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpen, LoaderCircle, X } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { authHeader } from '@/lib/auth'
import { cn } from '@/lib/utils'
import { LeftPage, RightPage, type Spread } from './pages'
import { webglAvailable } from './book-3d'

const Book3D = dynamic(() => import('./book-3d').then((m) => m.Book3D), { ssr: false, loading: () => null })

type Book = { textbook_id: string; title: string; spreads: Spread[]; completed: number }

const COPY: Record<Lang, Record<string, string>> = {
  fr: { lesson: 'Leçon', key: 'Formule clé', vocab: 'Vocabulaire', tapTerms: 'touche un mot', show: 'voir', predict: 'Prédis avant de regarder', flap: 'Pourquoi ? Réponds d’abord', right: 'Bien vu !', wrong: 'Pas tout à fait.', answerIs: 'La bonne réponse est', visual: 'Explication visuelle', explore: 'Explorer', rotate: 'Fais-le tourner', noVisual: 'Pas de schéma pour cette leçon : touche ici après l’avoir lue', reqAnswer: 'Prédiction répondue', reqFlap: 'Rabat « Pourquoi ? » ouvert', reqVocab: 'Vocabulaire lu', reqVisual: 'Visuel exploré', stamp: 'Leçon validée', stampHint: 'Le tampon arrive quand tout est fait', source: 'Pages du PDF :', building: 'Je prépare ton manuel…', buildingHint: 'Je découpe le contenu en leçons, je vérifie les formules et les réponses. Cela peut prendre une à deux minutes.', exit: 'Retour au tuteur', prev: 'Précédent', next: 'Suivant', done: 'leçons validées', error: 'Le manuel n’a pas pu être créé.', flat: 'Vue 2D', three: 'Vue 3D', of: 'sur', drag: 'Glisse pour tourner le modèle 3D' },
  en: { lesson: 'Lesson', key: 'Key formula', vocab: 'Vocabulary', tapTerms: 'tap a word', show: 'show', predict: 'Predict before you look', flap: 'Why? Answer first', right: 'Well spotted!', wrong: 'Not quite.', answerIs: 'The right answer is', visual: 'Visual explanation', explore: 'Explore', rotate: 'Turn it around', noVisual: 'No diagram for this lesson: tap here once you have read it', reqAnswer: 'Prediction answered', reqFlap: '“Why?” flap opened', reqVocab: 'Vocabulary read', reqVisual: 'Visual explored', stamp: 'Lesson done', stampHint: 'The stamp comes when everything is done', source: 'PDF pages:', building: 'Preparing your textbook…', buildingHint: 'Splitting the content into lessons, checking formulas and answers. This can take one or two minutes.', exit: 'Back to the tutor', prev: 'Previous', next: 'Next', done: 'lessons done', error: 'The textbook could not be created.', flat: '2D view', three: '3D view', of: 'of', drag: 'Drag to turn the 3D model' },
  ar: { lesson: 'الدرس', key: 'الصيغة الأساسية', vocab: 'المفردات', tapTerms: 'المس كلمة', show: 'عرض', predict: 'توقّع قبل أن ترى', flap: 'لماذا؟ أجب أولًا', right: 'أحسنت!', wrong: 'ليس تمامًا.', answerIs: 'الإجابة الصحيحة هي', visual: 'شرح مرئي', explore: 'استكشف', rotate: 'أدِره', noVisual: 'لا يوجد مخطط لهذا الدرس: المس هنا بعد قراءته', reqAnswer: 'أجبت عن التوقع', reqFlap: 'فتحت «لماذا؟»', reqVocab: 'قرأت المفردات', reqVisual: 'استكشفت المرئي', stamp: 'درس منجز', stampHint: 'يظهر الختم عند إنجاز كل شيء', source: 'صفحات الملف:', building: 'أُعدّ كتابك…', buildingHint: 'أقسّم المحتوى إلى دروس وأتحقق من الصيغ والإجابات. قد يستغرق ذلك دقيقة أو دقيقتين.', exit: 'العودة إلى المعلم', prev: 'السابق', next: 'التالي', done: 'دروس منجزة', error: 'تعذّر إنشاء الكتاب.', flat: 'عرض ثنائي الأبعاد', three: 'عرض ثلاثي الأبعاد', of: 'من', drag: 'اسحب لتدوير النموذج' },
}

export function TextbookView({ lang, source, onExit }: { lang: Lang; source: { docId?: string; text?: string }; onExit: () => void }) {
  const c = COPY[lang]
  const [book, setBook] = useState<Book | null>(null)
  const [error, setError] = useState('')
  const [index, setIndex] = useState(0)
  const [turning, setTurning] = useState<1 | -1 | 0>(0)
  const [mode, setMode] = useState<'3d' | '2d'>('2d')
  const [flip2d, setFlip2d] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    setMode(webglAvailable() && window.innerWidth >= 900 ? '3d' : '2d')
  }, [])

  useEffect(() => {
    if (started.current) return
    started.current = true
    fetch('/api/textbooks', { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify({ lang, doc_id: source.docId ?? null, text: source.docId ? null : source.text ?? null }) })
      .then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : `HTTP ${r.status}`); return d as Book })
      .then(setBook)
      .catch((e: Error) => setError(`${c.error} (${e.message})`))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const patch = useCallback((i: number, upd: Partial<Spread> & { prediction?: Spread['prediction'] }) => {
    setBook((b) => (b ? { ...b, spreads: b.spreads.map((s, k) => (k === i ? { ...s, ...upd } : s)), completed: b.spreads.filter((s, k) => (k === i ? upd.completed ?? s.completed : s.completed)).length } : b))
  }, [])

  async function call<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(`/engine/textbooks/${book!.textbook_id}/spreads/${index}/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify(body) })
    const d = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : `HTTP ${r.status}`)
    return d as T
  }

  const spread = book?.spreads[index]
  const onAnswer = async (choice: number) => {
    const r = await call<{ correct: boolean; correct_index: number; why: string; events: string[]; completed: boolean }>('answer', { choice })
    patch(index, { prediction: { ...spread!.prediction, choice, correct_index: r.correct_index, why: r.why, was_correct: r.correct }, events: r.events, completed: r.completed })
    // the flap swings open once the student chose: that opening counts as the flap interaction
    window.setTimeout(async () => { const f = await call<{ events: string[]; completed: boolean }>('event', { event: 'flap' }).catch(() => null); if (f) patch(index, { events: f.events, completed: f.completed }) }, 750)
  }
  const onEvent = async (name: 'vocab' | 'visual') => {
    if (!spread || spread.events.includes(name)) return
    const r = await call<{ events: string[]; completed: boolean }>('event', { event: name }).catch(() => null)
    if (r) patch(index, { events: r.events, completed: r.completed })
  }
  const go = (d: 1 | -1) => {
    if (!book || turning) return
    const n = index + d
    if (n < 0 || n >= book.spreads.length) return
    if (mode === '3d') { setTurning(d); setIndex(n) } else { setFlip2d(true); window.setTimeout(() => { setIndex(n); setFlip2d(false) }, 300) }
  }

  return (
    <section className="fixed inset-0 z-50 flex flex-col bg-[#2c241d] text-white" aria-label={book?.title ?? c.building}>
      <header className="z-10 flex flex-wrap items-center gap-3 border-b border-white/10 bg-[#2c241d]/95 px-4 py-3">
        <button type="button" onClick={onExit} className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 text-sm font-semibold hover:bg-white/20"><X className="size-4" />{c.exit}</button>
        <span className="inline-flex min-w-0 items-center gap-2 font-semibold"><BookOpen className="size-4 text-amber-300" /><span className="truncate">{book?.title ?? c.building}</span></span>
        {book ? (
          <div className="ms-auto flex items-center gap-2">
            <span className="text-xs text-white/70">{book.completed} {c.of} {book.spreads.length} {c.done}</span>
            <ol className="flex gap-1">{book.spreads.map((s, k) => <li key={k} className={cn('size-2.5 rounded-full', s.completed ? 'bg-emerald-400' : k === index ? 'bg-amber-300' : 'bg-white/25')} />)}</ol>
            <button type="button" onClick={() => setMode(mode === '3d' ? '2d' : '3d')} disabled={mode === '2d' && !webglAvailable()} className="rounded-full border border-white/20 px-3 py-1 text-xs font-semibold hover:bg-white/10 disabled:opacity-40">{mode === '3d' ? c.flat : c.three}</button>
          </div>
        ) : null}
      </header>

      {!book && !error ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
          <LoaderCircle className="size-10 animate-spin text-amber-300 motion-reduce:animate-none" />
          <p className="text-xl font-semibold">{c.building}</p>
          <p className="max-w-md text-sm text-white/70">{c.buildingHint}</p>
        </div>
      ) : null}
      {error ? <div className="m-6 rounded-2xl bg-red-500/15 p-5 text-red-200" role="alert">{error}</div> : null}

      {book && spread ? (
        mode === '3d' ? (
          <div className="relative min-h-0 flex-1">
            <Book3D spread={spread} index={index} copy={c} turning={turning} onTurned={() => setTurning(0)}
              onAnswer={onAnswer} onVocab={() => onEvent('vocab')} onVisual={() => onEvent('visual')} />
            {spread.model3d?.kind && spread.model3d.kind !== 'none' ? <p className="pointer-events-none absolute bottom-16 end-6 rounded-full bg-black/40 px-3 py-1 text-xs text-white/80">{c.drag}</p> : null}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto bg-[#3a2f26] p-4 [perspective:1600px] sm:p-8">
            <div className={cn('mx-auto grid max-w-5xl gap-0 rounded-xl bg-[#e2ad38] p-2 shadow-2xl transition-transform duration-300 md:grid-cols-2', flip2d && '[transform:rotateY(-8deg)] opacity-80')}>
              <div className="rounded-s-lg bg-[#fbf5e6] p-5 shadow-inner md:border-e md:border-black/10"><LeftPage key={`l${index}`} spread={spread} copy={c} number={index + 1} onAnswer={onAnswer} onVocab={() => onEvent('vocab')} /></div>
              <div className="rounded-e-lg bg-[#fbf5e6] p-5 shadow-inner"><RightPage key={`r${index}`} spread={spread} copy={c} onVisual={() => onEvent('visual')} has3d={false} /></div>
            </div>
          </div>
        )
      ) : null}

      {book ? (
        <footer className="z-10 flex items-center justify-between gap-3 border-t border-white/10 bg-[#2c241d]/95 px-4 py-3">
          <button type="button" onClick={() => go(-1)} disabled={index === 0 || !!turning} className="inline-flex items-center gap-2 rounded-xl bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/20 disabled:opacity-40"><ArrowLeft className="size-4 rtl:rotate-180" />{c.prev}</button>
          <span className="text-sm tabular-nums text-white/70">{c.lesson} {index + 1} {c.of} {book.spreads.length}</span>
          <button type="button" onClick={() => go(1)} disabled={index >= book.spreads.length - 1 || !!turning} className="inline-flex items-center gap-2 rounded-xl bg-amber-400 px-4 py-2 text-sm font-bold text-[#2c241d] hover:bg-amber-300 disabled:opacity-40">{c.next}<ArrowRight className="size-4 rtl:rotate-180" /></button>
        </footer>
      ) : null}
    </section>
  )
}
