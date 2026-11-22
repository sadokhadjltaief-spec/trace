'use client'

// Chapter page of the "Programme": the chapter's key notions, where to read the lesson (mourajaa.com for primary,
// najahni.tn for collège / lycée: the app only LINKS to these sites, it never downloads or copies their lessons) and a
// study plan for the chapter built by the TRACE engine without the LLM (POST /api/v1/curriculum/chapters/{id}/plan).
import { useEffect, useState } from 'react'
import { ArrowLeft, BookOpen, CalendarCheck, CheckCircle2, Download, ExternalLink, Info, LoaderCircle, Play, Target } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { MathText } from './math-text'
import { StudyPlanSession, type SessionPlan } from './study-plan-session'

type Tri = Record<string, string>
type SafeText = { text: string; shown_allowed: boolean }
type Detail = {
  chapter: { id: string; domain: string; title: Tri; notions: string[] }
  number: number
  level_id: string
  level_name: Tri
  cycle: string
  cycle_name: Tri
  domain_name: Tri
  resource: { name: string; url: string }
  disclaimer: Tri
}
type Plan = SessionPlan & { summary?: SafeText | null }

const COPY: Record<Lang, Record<string, string>> = {
  fr: { back: 'Retour au programme', chapter: 'Chapitre', notions: 'Notions clés', lesson: 'Le cours', lessonText: 'Lis la leçon de ce chapitre sur', open: 'Ouvrir le cours', pdf: 'Télécharger le PDF du cours', pdfNote: 'Le PDF se télécharge sur le site source. TRACE ne copie pas les cours.', plan: 'Générer un plan d’étude sur ce chapitre', planTitle: 'Ton plan d’étude', start: 'Commencer la session', day: 'Jour', min: 'min', error: 'Le chapitre n’a pas pu être chargé.', planError: 'Le plan n’a pas pu être généré.', site: 'Site source' },
  en: { back: 'Back to the programme', chapter: 'Chapter', notions: 'Key notions', lesson: 'The lesson', lessonText: 'Read this chapter’s lesson on', open: 'Open the lesson', pdf: 'Download the lesson PDF', pdfNote: 'The PDF is downloaded from the source site. TRACE does not copy lessons.', plan: 'Generate a study plan for this chapter', planTitle: 'Your study plan', start: 'Start the session', day: 'Day', min: 'min', error: 'The chapter could not be loaded.', planError: 'The plan could not be generated.', site: 'Source site' },
  ar: { back: 'العودة إلى البرنامج', chapter: 'الفصل', notions: 'المفاهيم الأساسية', lesson: 'الدرس', lessonText: 'اقرأ درس هذا الفصل على', open: 'افتح الدرس', pdf: 'حمّل ملف PDF للدرس', pdfNote: 'يُحمَّل الملف من الموقع المصدر. لا ينسخ TRACE الدروس.', plan: 'أنشئ خطة مراجعة لهذا الفصل', planTitle: 'خطة مراجعتك', start: 'ابدأ الجلسة', day: 'اليوم', min: 'د', error: 'تعذّر تحميل الفصل.', planError: 'تعذّر إنشاء الخطة.', site: 'الموقع المصدر' },
}
const CYCLE_STYLE: Record<string, string> = {
  primaire: 'from-amber-100 via-card to-orange-50 dark:from-amber-950/40',
  college: 'from-sky-100 via-card to-teal-50 dark:from-sky-950/40',
  lycee: 'from-violet-100 via-card to-fuchsia-50 dark:from-violet-950/40',
}
const shown = (s?: SafeText | null) => (s && s.shown_allowed ? s.text : '')

export function ChapterDetailView({ chapterId, lang, onBack }: { chapterId: string; lang: Lang; onBack: () => void }) {
  const c = COPY[lang]
  const pick = (t?: Tri) => (t ? t[lang] || t.fr : '')
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [plan, setPlan] = useState<Plan | null>(null)
  const [planBusy, setPlanBusy] = useState(false)
  const [planError, setPlanError] = useState('')
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    let live = true
    setD(null); setPlan(null); setError('')
    fetch(`/engine/curriculum/chapters/${encodeURIComponent(chapterId)}`)
      .then(async (r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return (await r.json()) as Detail })
      .then((x) => { if (live) setD(x) })
      .catch((e: Error) => { if (live) setError(`${c.error} (${e.message})`) })
    return () => { live = false }
  }, [chapterId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function makePlan() {
    setPlanBusy(true); setPlanError('')
    try {
      const r = await fetch(`/engine/curriculum/chapters/${encodeURIComponent(chapterId)}/plan?lang=${lang}`, { method: 'POST' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setPlan((await r.json()) as Plan)
      setTimeout(() => document.getElementById('chapter-plan')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    } catch (e) {
      setPlanError(`${c.planError} (${(e as Error).message})`)
    } finally {
      setPlanBusy(false)
    }
  }

  if (playing && plan) return <StudyPlanSession plan={plan} lang={lang} onExit={() => setPlaying(false)} />

  return (
    <section aria-labelledby="chapter-title" className="flex flex-col gap-6">
      <button type="button" onClick={onBack} className="inline-flex min-h-10 items-center gap-2 self-start rounded-lg px-2 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />{c.back}
      </button>

      {error ? <p role="alert" className="rounded-2xl bg-destructive/10 p-4 text-sm text-destructive">{error}</p> : null}
      {!d && !error ? <div className="flex justify-center py-16 text-muted-foreground"><LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" /></div> : null}

      {d ? (
        <>
          <header className={`flex flex-col gap-3 rounded-[2rem] border border-border bg-gradient-to-br p-6 shadow-sm sm:p-8 ${CYCLE_STYLE[d.cycle] ?? 'from-accent via-card to-secondary/70'}`}>
            <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
              <span className="rounded-full bg-primary px-3 py-1 text-primary-foreground">{pick(d.cycle_name)}</span>
              <span className="rounded-full border border-border bg-card px-3 py-1 text-foreground">{pick(d.level_name)}</span>
              <span className="rounded-full border border-border bg-card px-3 py-1 text-foreground">{pick(d.domain_name)}</span>
            </div>
            <p className="text-sm font-semibold uppercase tracking-wide text-primary">{c.chapter} {d.number}</p>
            <h1 id="chapter-title" className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">{pick(d.chapter.title)}</h1>
          </header>

          <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
            <div className="flex flex-col gap-3 rounded-3xl border border-border bg-card p-6 shadow-sm">
              <h2 className="flex items-center gap-2 text-lg font-bold text-foreground"><Target className="size-5 text-primary" aria-hidden="true" />{c.notions}</h2>
              <ul className="flex flex-col gap-2" lang="fr" dir="ltr">
                {d.chapter.notions.map((n) => (
                  <li key={n} className="flex items-start gap-2 rounded-xl bg-muted/50 px-3 py-2.5 text-sm text-foreground">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" /><MathText text={n} />
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex flex-col gap-4 rounded-3xl border border-border bg-card p-6 shadow-sm">
              <h2 className="flex items-center gap-2 text-lg font-bold text-foreground"><BookOpen className="size-5 text-primary" aria-hidden="true" />{c.lesson}</h2>
              <a href={d.resource.url} target="_blank" rel="noopener noreferrer" className="group flex items-center justify-between gap-3 rounded-2xl border border-border bg-muted/40 p-4 transition hover:border-primary/50 hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <span className="flex flex-col">
                  <span className="text-xs font-semibold text-muted-foreground">{c.site}</span>
                  <span className="text-lg font-bold text-foreground">{d.resource.name}</span>
                  <span className="text-sm text-muted-foreground">{c.lessonText} {d.resource.name}.</span>
                </span>
                <ExternalLink className="size-5 shrink-0 text-primary transition group-hover:translate-x-0.5" aria-hidden="true" />
              </a>
              <div className="flex flex-col gap-3 sm:flex-row">
                <a href={d.resource.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl border border-border px-4 py-2.5 font-semibold text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <Download className="size-4" aria-hidden="true" />{c.pdf}
                </a>
                <button type="button" onClick={makePlan} disabled={planBusy} className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60">
                  {planBusy ? <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <CalendarCheck className="size-4" aria-hidden="true" />}{c.plan}
                </button>
              </div>
              <p className="text-xs text-muted-foreground">{c.pdfNote}</p>
            </div>
          </div>

          {planError ? <p role="alert" className="rounded-2xl bg-destructive/10 p-4 text-sm text-destructive">{planError}</p> : null}

          {plan ? (
            <div id="chapter-plan" className="flex flex-col gap-5 rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-8">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-primary">{c.planTitle}</p>
                  <h2 className="text-2xl font-bold text-foreground">{shown(plan.title)}</h2>
                  {shown(plan.summary) ? <p className="mt-1 max-w-2xl text-muted-foreground">{shown(plan.summary)}</p> : null}
                </div>
                <button type="button" onClick={() => setPlaying(true)} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <Play className="size-4" aria-hidden="true" />{c.start}
                </button>
              </div>
              <ol className="relative flex flex-col gap-4 border-s-2 border-primary/30 ps-6">
                {plan.days.map((day) => (
                  <li key={day.day} className="relative rounded-2xl border border-border bg-muted/30 p-4">
                    <span className="absolute -start-[2.15rem] top-4 flex size-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">{day.day}</span>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="font-bold text-foreground"><MathText text={shown(day.title)} /></h3>
                      {day.duration_min ? <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-accent-foreground">{day.duration_min} {c.min}</span> : null}
                    </div>
                    <ul className="mt-2 flex flex-col gap-1.5">
                      {day.tasks.map((t, i) => shown(t) ? (
                        <li key={i} className="flex items-start gap-2 text-sm text-foreground"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" /><MathText text={shown(t)} /></li>
                      ) : null)}
                    </ul>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          <p className="flex items-start gap-2 rounded-2xl border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
            <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />{pick(d.disclaimer)}
          </p>
        </>
      ) : null}
    </section>
  )
}
