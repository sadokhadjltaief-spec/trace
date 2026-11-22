'use client'

// Study session: follows the plan day by day. Each step shows the day's focus, goals and tasks (tick them off) and
// the text of one page of the student's own file (extracted by the TRACE engine, headers/footers removed; this text
// is the student's material, not generated). "Précédent" / "Suivant" move page by page across the days.
import { useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, Circle, Clock, PartyPopper } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { cn } from '@/lib/utils'
import { PageText } from './page-text'
import { MathText } from './math-text'

type SafeText = { text: string; shown_allowed: boolean }
export type SessionPlan = {
  title: SafeText
  days: { day: number; title: SafeText; goals: SafeText[]; tasks: SafeText[]; sources: { file: string; page: number }[]; duration_min?: number | null }[]
  page_texts?: { file: string; page: number; text: string }[]
}

const COPY: Record<Lang, Record<string, string>> = {
  en: { back: 'Back to the plan', day: 'Day', page: 'Page', of: 'of', prev: 'Previous', next: 'Next', nextDay: 'Next day', goals: 'Goals', tasks: 'Tasks', content: 'Course content', noText: 'This day has no page attached: work on the tasks above.', finish: 'Finish the session', done: 'Session finished', doneText: 'You went through every day of the plan.', min: 'min', source: 'Text from your file' },
  fr: { back: 'Retour au plan', day: 'Jour', page: 'Page', of: 'sur', prev: 'Précédent', next: 'Suivant', nextDay: 'Jour suivant', goals: 'Objectifs', tasks: 'Tâches', content: 'Contenu du cours', noText: 'Ce jour n’a pas de page associée : travaille les tâches ci-dessus.', finish: 'Terminer la session', done: 'Session terminée', doneText: 'Tu as parcouru tous les jours du plan.', min: 'min', source: 'Texte de ton fichier' },
  ar: { back: 'العودة إلى الخطة', day: 'اليوم', page: 'الصفحة', of: 'من', prev: 'السابق', next: 'التالي', nextDay: 'اليوم التالي', goals: 'الأهداف', tasks: 'المهام', content: 'محتوى الدرس', noText: 'لا توجد صفحة لهذا اليوم: اشتغل على المهام أعلاه.', finish: 'أنهِ الجلسة', done: 'انتهت الجلسة', doneText: 'مررت بكل أيام الخطة.', min: 'د', source: 'نصّ من ملفك' },
}
const shown = (s?: SafeText | null) => (s && s.shown_allowed ? s.text : '')

export function StudyPlanSession({ plan, lang, onExit }: { plan: SessionPlan; lang: Lang; onExit: () => void }) {
  const c = COPY[lang]
  const texts = useMemo(() => new Map((plan.page_texts ?? []).map((p) => [`${p.file}#${p.page}`, p.text])), [plan])
  // one step per (day, page); a day without pages is one step with its tasks only
  type Step = { di: number; pi: number; pages: number; src: { file: string; page: number } | null }
  const steps = useMemo<Step[]>(
    () =>
      plan.days.flatMap((d, di): Step[] => {
        const pages = d.sources.filter((s) => texts.has(`${s.file}#${s.page}`))
        return pages.length ? pages.map((s, pi) => ({ di, pi, pages: pages.length, src: s })) : [{ di, pi: 0, pages: 0, src: null }]
      }),
    [plan, texts],
  )
  const [i, setI] = useState(0)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [finished, setFinished] = useState(false)
  const step = steps[i]
  const day = plan.days[step?.di ?? 0]

  const header = (
    <button type="button" onClick={onExit} className="inline-flex min-h-10 items-center gap-2 self-start rounded-lg px-2 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
      {c.back}
    </button>
  )

  if (finished || !step) {
    return (
      <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
          {header}
          <div className="flex flex-col items-center rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
            <span className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-secondary text-primary">
              <PartyPopper className="size-8" aria-hidden="true" />
            </span>
            <h1 className="text-2xl font-bold text-foreground">{c.done}</h1>
            <p className="mt-2 text-muted-foreground">{c.doneText}</p>
            <button type="button" onClick={onExit} className="mt-7 inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              {c.back}
            </button>
          </div>
        </div>
      </section>
    )
  }

  const isLast = i === steps.length - 1
  const nextIsNewDay = !isLast && steps[i + 1].di !== step.di
  const pageText = step.src ? texts.get(`${step.src.file}#${step.src.page}`) ?? '' : ''

  return (
    <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12" aria-labelledby="session-day">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        {header}

        <div className="flex flex-col gap-4 rounded-[2rem] border border-border bg-gradient-to-br from-primary/15 via-card to-brand-cyan/10 p-5 shadow-sm sm:p-6">
          <p className="text-lg font-bold leading-snug text-foreground sm:text-xl">{shown(plan.title)}</p>
          <ol className="flex flex-wrap gap-2" aria-label={c.day}>
            {plan.days.map((d, di) => {
              const first = steps.findIndex((x) => x.di === di)
              return (
                <li key={d.day} className="min-w-0 flex-1 basis-24">
                  <button type="button" onClick={() => first >= 0 && setI(first)} aria-current={di === step.di ? 'step' : undefined}
                    className={cn('flex w-full flex-col gap-1.5 rounded-xl px-2 py-1.5 text-start transition hover:bg-background/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring')}>
                    <span className={cn('text-xs font-bold', di === step.di ? 'text-primary' : 'text-muted-foreground')}>{c.day} {d.day}</span>
                    <span className={cn('h-1.5 w-full rounded-full', di < step.di ? 'bg-primary' : di === step.di ? 'bg-gradient-to-r from-primary to-brand-cyan' : 'bg-primary/20')} />
                  </button>
                </li>
              )
            })}
          </ol>
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
          <aside className="flex flex-col gap-4 self-start rounded-3xl border border-border bg-card p-6 shadow-sm lg:sticky lg:top-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-primary">{c.day} {day.day} {c.of} {plan.days.length}</p>
              <h1 id="session-day" className="mt-1 text-xl font-bold leading-snug text-foreground"><MathText text={shown(day.title)} /></h1>
              {day.duration_min ? (
                <p className="mt-1 inline-flex items-center gap-1.5 text-sm text-muted-foreground"><Clock className="size-4" aria-hidden="true" />{day.duration_min} {c.min}</p>
              ) : null}
            </div>
            {day.goals.filter(shown).length ? (
              <div>
                <p className="text-sm font-semibold text-foreground">{c.goals}</p>
                <ul className="mt-1.5 flex list-disc flex-col gap-1 ps-5 text-sm text-muted-foreground">
                  {day.goals.map(shown).filter(Boolean).map((g, k) => <li key={k}><MathText text={g} /></li>)}
                </ul>
              </div>
            ) : null}
            <div>
              <p className="text-sm font-semibold text-foreground">{c.tasks}</p>
              <ul className="mt-2 flex flex-col gap-2">
                {day.tasks.map(shown).filter(Boolean).map((tk, k) => {
                  const id = `${step.di}-${k}`
                  const on = checked.has(id)
                  return (
                    <li key={id}>
                      <button
                        type="button"
                        aria-pressed={on}
                        onClick={() => setChecked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })}
                        className="flex w-full items-start gap-2.5 rounded-xl border border-border bg-background/70 px-3 py-2.5 text-start text-sm transition hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {on ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" /> : <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
                        <span className={cn('text-foreground', on && 'text-muted-foreground line-through')}><MathText text={tk} /></span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          </aside>

          <article className="flex min-h-[28rem] flex-col rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-8" aria-label={c.content}>
            <div className="flex items-center justify-between gap-3 border-b border-border pb-4">
              <span className="inline-flex min-w-0 items-center gap-2.5 text-sm font-semibold text-foreground">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-secondary text-primary"><BookOpen className="size-4" aria-hidden="true" /></span>
                <span className="flex min-w-0 flex-col"><span className="truncate">{step.src ? step.src.file : c.content}</span>{step.src ? <span className="text-xs font-normal text-muted-foreground">{c.page} {step.src.page}</span> : null}</span>
              </span>
              {step.pages ? <span className="text-xs tabular-nums text-muted-foreground">{step.pi + 1} {c.of} {step.pages}</span> : null}
            </div>
            {pageText ? (
              <div className="mt-5 flex-1"><PageText text={pageText} /></div>
            ) : (
              <p className="mt-4 flex-1 text-muted-foreground">{c.noText}</p>
            )}
            {pageText ? <p className="mt-4 text-xs text-muted-foreground">{c.source}</p> : null}
          </article>
        </div>

        <div className="flex items-center justify-between gap-3">
          <button type="button" disabled={i === 0} onClick={() => setI((n) => Math.max(0, n - 1))} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-border bg-card px-5 py-2.5 font-semibold text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
            <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
            {c.prev}
          </button>
          <span className="text-sm tabular-nums text-muted-foreground">{i + 1} / {steps.length}</span>
          <button type="button" onClick={() => (isLast ? setFinished(true) : setI((n) => n + 1))} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {isLast ? c.finish : nextIsNewDay ? c.nextDay : c.next}
            <ArrowRight className="size-4 rtl:rotate-180" aria-hidden="true" />
          </button>
        </div>
      </div>
    </section>
  )
}
