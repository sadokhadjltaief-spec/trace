'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, Check, CircleCheck, Gamepad2, LoaderCircle } from 'lucide-react'
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
    if (usesEngine) {
      const form = new FormData()
      ;(files ?? []).forEach((f) => form.append('files', f))
      form.append('details', details)
      form.append('lang', lang)
      if (kind !== 'plan') {
        form.append('text', material ?? '')
        form.append('source', source ?? 'file')
      }
      // study plan: Next route; quiz / flashcards: the /engine rewrite to the TRACE API
      const url = kind === 'plan' ? '/api/study-plan' : kind === 'quiz' ? '/engine/practice/quiz' : '/engine/practice/cards'
      fetch(url, { method: 'POST', body: form })
        .then(async (r) => {
          const data = await r.json().catch(() => ({}))
          if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : PLAN_COPY[lang].error)
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
          setPlanError(e.message || PLAN_COPY[lang].error)
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
            <div className="mt-6 flex flex-col gap-3">
              {shown(plan.title) ? <p className="text-base font-semibold text-foreground">{shown(plan.title)}</p> : null}
              {shown(plan.summary) ? <p className="text-sm text-muted-foreground">{shown(plan.summary)}</p> : null}
              {plan.targeted_at ? (
                <p className="text-sm font-medium text-foreground">
                  {PLAN_COPY[lang].targeted} : {lang === 'fr' ? plan.targeted_at.name_fr : lang === 'ar' ? plan.targeted_at.name_ar : plan.targeted_at.name_en}
                </p>
              ) : null}
              {plan.days.map((d) => (
                <div key={d.day} className="rounded-2xl border border-border bg-background/70 p-4">
                  <p className="text-sm font-semibold text-foreground">{PLAN_COPY[lang].day} {d.day} · {shown(d.title)}{d.duration_min ? ` · ${d.duration_min} min` : ''}</p>
                  {d.goals.filter(shown).length ? (
                    <p className="mt-1 text-sm text-muted-foreground">{d.goals.map(shown).filter(Boolean).join(' · ')}</p>
                  ) : null}
                  <ul className="mt-2 flex list-disc flex-col gap-1 ps-5 text-sm text-foreground">
                    {d.tasks.map(shown).filter(Boolean).map((tk, i) => <li key={i}>{tk}</li>)}
                  </ul>
                  {d.sources.length ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {PLAN_COPY[lang].pages} : {d.sources.map((s) => `${s.file} p. ${s.page}`).join(' · ')}
                    </p>
                  ) : null}
                </div>
              ))}
              {(plan.formulas ?? []).filter(shown).length ? (
                <div className="rounded-2xl border border-border bg-background/70 p-4">
                  <p className="text-sm font-semibold text-foreground">{PLAN_COPY[lang].formulas}</p>
                  <ul className="mt-2 flex list-disc flex-col gap-1 ps-5 text-sm text-foreground" dir="ltr">
                    {(plan.formulas ?? []).map(shown).filter(Boolean).map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                </div>
              ) : null}
              {plan.check_questions.filter(shown).length ? (
                <div className="rounded-2xl border border-border bg-background/70 p-4">
                  <p className="text-sm font-semibold text-foreground">{PLAN_COPY[lang].check}</p>
                  <ul className="mt-2 flex list-disc flex-col gap-1 ps-5 text-sm text-foreground">
                    {plan.check_questions.map(shown).filter(Boolean).map((q, i) => <li key={i}>{q}</li>)}
                  </ul>
                </div>
              ) : null}
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
