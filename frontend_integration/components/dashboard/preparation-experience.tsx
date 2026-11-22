'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, BookOpen, CalendarDays, Check, CircleCheck, Clock, Gamepad2, HelpCircle, LoaderCircle, Sigma, Target } from 'lucide-react'
import { MathText } from './math-text'

// one colour per day of the plan (rotates)
const DAY_TONES = [
  { badge: 'bg-primary text-primary-foreground', dot: 'bg-primary', chip: 'bg-primary/10 text-primary-deep' },
  { badge: 'bg-brand-cyan text-white', dot: 'bg-brand-cyan', chip: 'bg-brand-cyan/15 text-brand-cyan' },
  { badge: 'bg-emerald-500 text-white', dot: 'bg-emerald-500', chip: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' },
  { badge: 'bg-violet-500 text-white', dot: 'bg-violet-500', chip: 'bg-violet-500/15 text-violet-600 dark:text-violet-400' },
  { badge: 'bg-rose-500 text-white', dot: 'bg-rose-500', chip: 'bg-rose-500/15 text-rose-600 dark:text-rose-400' },
]
import type { DashboardCopy } from './dashboard-copy'
import type { Lang } from '@/lib/translations'
import { HighwayGame } from './highway-game'
import { QuizPlayer, type PracticeQuiz } from './quiz-player'
import { FlashcardPlayer } from './flashcard-player'
import { StudyPlanSession } from './study-plan-session'

type FlowKind = 'quiz' | 'plan' | 'flashcards'

type Props = {
  copy: DashboardCopy
  kind: FlowKind
  fileNames: string[]
  details: string
  lang: Lang
  onBack: () => void
  files?: File[] // the uploaded files, sent to the TRACE engine (study plan, quiz, flashcards)
  text?: string // quiz / flashcards: pasted text or link
  source?: string // quiz / flashcards: file | text | youtube | wikipedia
}

export type PracticeCards = {
  deck_id: string
  cards: { id: string; front: { text: string; shown_allowed: boolean }; back: { text: string; shown_allowed: boolean } }[]
  note: string
  refused: string | null
}
const ERROR_COPY: Record<Lang, Record<'quiz' | 'plan' | 'flashcards', string>> = {
  en: { quiz: 'The quiz could not be created.', plan: 'The plan could not be created.', flashcards: 'The flashcards could not be created.' },
  fr: { quiz: 'Le quiz n’a pas pu être créé.', plan: 'Le plan n’a pas pu être créé.', flashcards: 'Les cartes n’ont pas pu être créées.' },
  ar: { quiz: 'تعذّر إنشاء الاختبار.', plan: 'تعذّر إنشاء الخطة.', flashcards: 'تعذّر إنشاء البطاقات.' },
}

const START_COPY: Record<Lang, { quiz: string; cards: string; plan: string }> = {
  en: { quiz: 'Start the quiz', cards: 'Start', plan: 'Start the session' },
  fr: { quiz: 'Commencer le quiz', cards: 'Commencer', plan: 'Commencer la session' },
  ar: { quiz: 'ابدأ الاختبار', cards: 'ابدأ', plan: 'ابدأ الجلسة' },
}

// TRACE engine study plan (C:\TRACE\engine\study_plan.py). Texts arrive checked by the engine's guards.
type SafeText = { text: string; shown_allowed: boolean }
type PlanDay = { day: number; title: SafeText; goals: SafeText[]; tasks: SafeText[]; sources: { file: string; page: number }[]; duration_min?: number | null }
type StudyPlan = {
  title: SafeText
  summary: SafeText | null
  days: PlanDay[]
  check_questions: SafeText[]
  formulas?: SafeText[]
  page_texts?: { file: string; page: number; text: string }[]
  targeted_at: { name_en: string; name_fr: string; name_ar: string } | null
  refused: string | null
}
const PLAN_COPY: Record<Lang, { day: string; pages: string; check: string; targeted: string; error: string; formulas: string }> = {
  en: { day: 'Day', pages: 'Pages', check: 'Check yourself', targeted: 'Targeted at', error: 'The plan could not be created.', formulas: 'Key formulas' },
  fr: { day: 'Jour', pages: 'Pages', check: 'Vérifie-toi', targeted: 'Ciblé sur', error: 'Le plan n’a pas pu être créé.', formulas: 'Formules clés' },
  ar: { day: 'اليوم', pages: 'الصفحات', check: 'تحقّق من نفسك', targeted: 'موجّه إلى', error: 'تعذّر إنشاء الخطة.', formulas: 'الصيغ الأساسية' },
}
const shown = (s: SafeText | null | undefined) => (s && s.shown_allowed && s.text ? s.text : '')

const GAME_COPY: Record<Lang, { description: string }> = {
  en: { description: 'Dodge traffic and chase your high score.' },
  fr: { description: 'Évite les voitures et bats ton meilleur score.' },
  ar: { description: 'تفادَ السيارات وحاول تحطيم رقمك القياسي.' },
}

const FLOW_COPY: Record<Lang, { preparing: string; ready: string }> = {
  en: { preparing: 'Preparing your flashcards', ready: 'Your flashcards are ready to go' },
  fr: { preparing: 'Préparation de tes cartes mémo', ready: 'Tes cartes mémo sont prêtes' },
  ar: { preparing: 'جارٍ تجهيز بطاقات المراجعة', ready: 'بطاقات المراجعة جاهزة' },
}

export function PreparationExperience({ copy, kind, fileNames, details, lang, onBack, files, text: material, source }: Props) {
  const [progress, setProgress] = useState(0)
  const [ready, setReady] = useState(false)
  const [gameOpen, setGameOpen] = useState(false)
  const [plan, setPlan] = useState<StudyPlan | null>(null)
  const [planError, setPlanError] = useState<string | null>(null)
  const [quiz, setQuiz] = useState<PracticeQuiz | null>(null)
  const [cards, setCards] = useState<PracticeCards | null>(null)
  const [playing, setPlaying] = useState(false)
  const started = useRef(false) // React dev mode runs effects twice: send the request only once
  const text = copy.preparation
  const hasMaterial = (!!files && files.length > 0) || !!material?.trim()
  const usesEngine = kind === 'plan' ? !!files && files.length > 0 : hasMaterial

  useEffect(() => {
    const startedAt = Date.now()
    let done = false
    const timer = window.setInterval(() => {
      // with the engine, the bar waits at 90 % until the plan has arrived
      const next = Math.min(usesEngine ? 90 : 100, Math.round(((Date.now() - startedAt) / 16000) * 100))
      if (!done) setProgress(next)
      if (!usesEngine && next === 100) {
        window.clearInterval(timer)
        setReady(true)
        setGameOpen(false)
      }
    }, 100)
    if (usesEngine && !started.current) {
      started.current = true
      const form = new FormData()
      ;(files ?? []).forEach((f) => form.append('files', f))
      form.append('details', details)
      form.append('lang', lang)
      if (kind !== 'plan') {
        form.append('text', material ?? '')
        form.append('source', source ?? 'file')
      }
      // Next route handlers (they wait for long generations; the /engine rewrite proxy would time out)
      const url = kind === 'plan' ? '/api/study-plan' : kind === 'quiz' ? '/api/practice/quiz' : '/api/practice/cards'
      fetch(url, { method: 'POST', body: form })
        .then(async (r) => {
          const data = await r.json().catch(() => ({}))
          if (!r.ok) throw new Error(`${ERROR_COPY[lang][kind]} (${typeof data.detail === 'string' ? data.detail : 'HTTP ' + r.status})`)
          return data
        })
        .then((p) => {
          done = true
          window.clearInterval(timer)
          if (p.refused) setPlanError(p.refused)
          if (kind === 'plan') setPlan(p as StudyPlan)
          else if (kind === 'quiz') setQuiz(p as PracticeQuiz)
          else setCards(p as PracticeCards)
          setProgress(100)
          setReady(true)
          setGameOpen(false)
        })
        .catch((e: Error) => {
          done = true
          window.clearInterval(timer)
          setPlanError(e.message || ERROR_COPY[lang][kind])
          setProgress(100)
          setReady(true)
        })
    }
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (playing && quiz && quiz.questions.length) {
    return <QuizPlayer quiz={quiz} lang={lang} onExit={() => setPlaying(false)} />
  }
  if (playing && cards && cards.cards.length) {
    return <FlashcardPlayer deck={cards} lang={lang} onExit={() => setPlaying(false)} />
  }
  if (playing && plan && plan.days.length) {
    return <StudyPlanSession plan={plan} lang={lang} onExit={() => setPlaying(false)} />
  }

  return (
    <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12" aria-labelledby="preparation-title">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <button type="button" onClick={onBack} className="inline-flex min-h-10 items-center gap-2 self-start rounded-lg px-2 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
          {text.back}
        </button>

        <div className="rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-9">
          <div className="flex flex-col items-center text-center">
            <span className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-secondary text-primary">
              {ready ? <CircleCheck className="size-7" aria-hidden="true" /> : <LoaderCircle className="size-7 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            </span>
            <h1 id="preparation-title" className="text-balance text-2xl font-bold text-foreground sm:text-3xl">
              {kind === 'flashcards' ? (ready ? FLOW_COPY[lang].ready : FLOW_COPY[lang].preparing) : ready ? (kind === 'quiz' ? text.readyQuiz : text.readyPlan) : (kind === 'quiz' ? text.preparingQuiz : text.preparingPlan)}
            </h1>
            <p className="mt-2 max-w-lg text-pretty text-sm leading-relaxed text-muted-foreground sm:text-base">
              {ready ? text.readyDescription : text.preparingDescription}
            </p>
          </div>

          <div className="mt-8">
            <div className="mb-2 flex items-center justify-between gap-3 text-sm">
              <span className="font-medium text-foreground">{text.progress}</span>
              <span className="tabular-nums text-muted-foreground" aria-hidden="true">{progress}%</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={text.progress} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
              <div className="h-full rounded-full bg-gradient-to-r from-primary to-brand-cyan transition-[width] duration-200 ease-linear" style={{ width: `${progress}%` }} />
            </div>
          </div>

          <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-border bg-background/70 p-4 sm:flex-row sm:items-start">
            <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-foreground">{fileNames.join(', ')}</p>
              {details.trim() ? <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{details}</p> : null}
            </div>
            <span className="shrink-0 text-xs font-medium text-muted-foreground">{text.sourceIncluded}</span>
          </div>

          {!ready ? (
            <div className="mt-6 flex flex-col items-center gap-3">
              <button type="button" onClick={() => setGameOpen((open) => !open)} aria-expanded={gameOpen} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition hover:border-primary/50 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Gamepad2 className="size-4" aria-hidden="true" />
                {gameOpen ? text.hideGame : text.playGame}
              </button>
              <p className="text-center text-xs text-muted-foreground">{GAME_COPY[lang].description}</p>
            </div>
          ) : null}
          {ready && usesEngine && planError ? (
            <p className="mt-6 rounded-2xl border border-border bg-background/70 p-4 text-sm text-muted-foreground">{planError}</p>
          ) : null}
          {ready && plan && !plan.refused ? (
            <div className="mt-8 flex flex-col gap-5 text-start">
              <div className="relative overflow-hidden rounded-3xl border border-border bg-gradient-to-br from-primary/15 via-card to-brand-cyan/15 p-6 sm:p-7">
                <div className="absolute -end-10 -top-12 size-40 rounded-full bg-primary/15 blur-3xl" aria-hidden="true" />
                <div className="relative flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1 text-xs font-bold text-primary-foreground"><CalendarDays className="size-3.5" aria-hidden="true" />{plan.days.length} {({ en: 'days', fr: 'jours', ar: 'أيام' } as const)[lang]}</span>
                    {plan.days.some((d) => d.duration_min) ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-cyan/15 px-3 py-1 text-xs font-bold text-brand-cyan"><Clock className="size-3.5" aria-hidden="true" />{plan.days.reduce((n, d) => n + (d.duration_min ?? 0), 0)} min</span>
                    ) : null}
                  </div>
                  {shown(plan.title) ? <h2 className="text-balance text-2xl font-bold leading-tight text-foreground sm:text-3xl">{shown(plan.title)}</h2> : null}
                  {shown(plan.summary) ? <p className="max-w-2xl text-pretty leading-relaxed text-muted-foreground">{shown(plan.summary)}</p> : null}
                  {plan.targeted_at ? (
                    <p className="inline-flex w-fit items-center gap-2 rounded-xl bg-background/80 px-3 py-2 text-sm font-semibold text-foreground"><Target className="size-4 text-primary" aria-hidden="true" />
                      {PLAN_COPY[lang].targeted} : {lang === 'fr' ? plan.targeted_at.name_fr : lang === 'ar' ? plan.targeted_at.name_ar : plan.targeted_at.name_en}
                    </p>
                  ) : null}
                </div>
              </div>

              <ol className="relative flex flex-col gap-4 sm:ps-6">
                <span className="absolute bottom-6 start-[0.7rem] top-6 hidden w-0.5 rounded-full bg-gradient-to-b from-primary via-brand-cyan to-emerald-500/60 sm:block" aria-hidden="true" />
                {plan.days.map((d, di) => {
                  const tone = DAY_TONES[di % DAY_TONES.length]
                  return (
                    <li key={d.day} className="relative">
                      <span className={`absolute -start-[1.05rem] top-7 hidden size-3.5 rounded-full ring-4 ring-card sm:block ${tone.dot}`} aria-hidden="true" />
                      <div className="rounded-3xl border border-border bg-card p-5 shadow-sm transition hover:border-primary/40 hover:shadow-md sm:p-6">
                        <div className="flex items-start gap-4">
                          <span className={`flex size-12 shrink-0 flex-col items-center justify-center rounded-2xl text-center leading-none ${tone.badge}`}>
                            <span className="text-[10px] font-bold uppercase tracking-wide">{PLAN_COPY[lang].day}</span>
                            <span className="text-lg font-extrabold">{d.day}</span>
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <h3 className="text-lg font-bold leading-snug text-foreground">{shown(d.title)}</h3>
                              {d.duration_min ? <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs font-semibold text-muted-foreground"><Clock className="size-3.5" aria-hidden="true" />{d.duration_min} min</span> : null}
                            </div>
                            {d.goals.filter(shown).length ? (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {d.goals.map(shown).filter(Boolean).map((g, k) => <span key={k} className={`rounded-full px-2.5 py-1 text-xs font-semibold ${tone.chip}`}>{g}</span>)}
                              </div>
                            ) : null}
                          </div>
                        </div>
                        <ul className="mt-4 flex flex-col gap-2">
                          {d.tasks.map(shown).filter(Boolean).map((tk, k) => (
                            <li key={k} className="flex items-start gap-2.5 rounded-xl bg-muted/50 px-3 py-2.5 text-sm leading-relaxed text-foreground">
                              <CircleCheck className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                              <span><MathText text={tk} /></span>
                            </li>
                          ))}
                        </ul>
                        {d.sources.length ? (
                          <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                            <BookOpen className="size-3.5" aria-hidden="true" />{PLAN_COPY[lang].pages} :
                            {d.sources.map((s, k) => <span key={k} title={s.file} className="rounded-full border border-border bg-background px-2 py-0.5 font-semibold text-foreground" dir="ltr">p. {s.page}</span>)}
                          </div>
                        ) : null}
                      </div>
                    </li>
                  )
                })}
              </ol>

              <div className="grid gap-4 md:grid-cols-2">
                {(plan.formulas ?? []).filter(shown).length ? (
                  <div className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6">
                    <p className="flex items-center gap-2 font-bold text-foreground"><span className="flex size-8 items-center justify-center rounded-xl bg-brand-cyan/15 text-brand-cyan"><Sigma className="size-4" aria-hidden="true" /></span>{PLAN_COPY[lang].formulas}</p>
                    <ul className="mt-3 flex flex-col gap-2">
                      {(plan.formulas ?? []).map(shown).filter(Boolean).map((f, k) => <li key={k} className="rounded-xl bg-muted/50 px-3 py-2 text-sm text-foreground"><MathText text={f} formula /></li>)}
                    </ul>
                  </div>
                ) : null}
                {plan.check_questions.filter(shown).length ? (
                  <div className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-6">
                    <p className="flex items-center gap-2 font-bold text-foreground"><span className="flex size-8 items-center justify-center rounded-xl bg-primary/15 text-primary"><HelpCircle className="size-4" aria-hidden="true" /></span>{PLAN_COPY[lang].check}</p>
                    <ol className="mt-3 flex flex-col gap-2">
                      {plan.check_questions.map(shown).filter(Boolean).map((q, k) => (
                        <li key={k} className="flex items-start gap-2.5 rounded-xl bg-muted/50 px-3 py-2 text-sm text-foreground">
                          <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-[11px] font-bold text-primary-foreground">{k + 1}</span>
                          <span><MathText text={q} /></span>
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
          {ready && quiz && !quiz.refused && quiz.questions.length ? (
            <p className="mt-6 text-center text-sm text-muted-foreground">{quiz.questions.length} questions · {quiz.verification}</p>
          ) : null}
          {ready && cards && !cards.refused && cards.cards.length ? (
            <p className="mt-6 text-center text-sm text-muted-foreground">{cards.cards.length} · {cards.note}</p>
          ) : null}
          {ready ? (
            <div className="mt-7 flex flex-col-reverse justify-center gap-3 sm:flex-row">
              {plan && !plan.refused && plan.days.length ? (
                <button type="button" onClick={() => setPlaying(true)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  {START_COPY[lang].plan}
                </button>
              ) : null}
              {cards && !cards.refused && cards.cards.length ? (
                <button type="button" onClick={() => setPlaying(true)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  {START_COPY[lang].cards}
                </button>
              ) : null}
              {quiz && !quiz.refused && quiz.questions.length ? (
                <button type="button" onClick={() => setPlaying(true)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  {START_COPY[lang].quiz}
                </button>
              ) : null}
              <button type="button" onClick={onBack} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {text.done}
                <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
              </button>
            </div>
          ) : null}
        </div>

        {gameOpen && !ready ? <HighwayGame lang={lang} /> : null}
      </div>
    </section>
  )
}
