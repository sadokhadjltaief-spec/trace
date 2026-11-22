'use client'

// "My progress": the student's learning memory from the TRACE engine (GET /api/v1/students/me/progress).
// Every number comes from the tutor's observations of this student (counts); the status of a notion is computed by
// the engine (one exchange never decides it). No forecast and no invented score is shown.
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, BarChart3, CheckCircle2, Clock3, Info, LoaderCircle, MessageSquare, Sparkles, Target } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { authHeader, savedSession } from '@/lib/auth'
import { cn } from '@/lib/utils'

type Concept = { concept: string; subject: string; understood: number; struggling: number; misconception: number; signals: number; mastery: number; status: 'mastered' | 'in_progress' | 'to_review'; last_note: string; helped_by: string }
type Progress = { concepts: Concept[]; by_subject: Record<string, number>; counts: Record<string, number>; sessions: number; messages: number; insight: string }

const C: Record<Lang, Record<string, string>> = {
  fr: { title: 'Ma progression', intro: 'Ce que tu as montré en discutant avec le tuteur. Chaque échange ajoute un signal.', insight: 'Ce que je remarque', mastered: 'Maîtrisé', in_progress: 'En cours', to_review: 'À revoir', sessions: 'Séances', messages: 'Messages', heat: 'Carte de maîtrise', heatSub: 'Notions × signaux observés', understood: 'Compris', struggling: 'Difficulté', misconception: 'Idée fausse', mastery: 'Maîtrise', subjects: 'Maîtrise moyenne par matière', empty: 'Pas encore de données. Pose des questions au tuteur et réponds à ses questions : tes progrès apparaîtront ici.', guest: 'Connecte-toi pour garder ta progression.', note: 'Calculé à partir de tes échanges. Aucune prévision, aucune note inventée. Le statut d’une notion demande au moins deux signaux.', legendLow: 'Peu de signaux', legendHigh: 'Beaucoup', error: 'La progression n’a pas pu être chargée.' },
  en: { title: 'My progress', intro: 'What you showed while talking with the tutor. Each exchange adds a signal.', insight: 'What I notice', mastered: 'Mastered', in_progress: 'In progress', to_review: 'To review', sessions: 'Sessions', messages: 'Messages', heat: 'Mastery map', heatSub: 'Notions × observed signals', understood: 'Understood', struggling: 'Struggled', misconception: 'Misconception', mastery: 'Mastery', subjects: 'Average mastery by subject', empty: 'No data yet. Ask the tutor questions and answer its questions: your progress will appear here.', guest: 'Sign in to keep your progress.', note: 'Computed from your exchanges. No forecast, no invented score. A notion’s status needs at least two signals.', legendLow: 'Few signals', legendHigh: 'Many', error: 'Progress could not be loaded.' },
  ar: { title: 'تقدّمي', intro: 'ما أظهرته أثناء حديثك مع المعلّم. كل تبادل يضيف إشارة.', insight: 'ما ألاحظه', mastered: 'متقن', in_progress: 'قيد التعلّم', to_review: 'للمراجعة', sessions: 'الحصص', messages: 'الرسائل', heat: 'خريطة الإتقان', heatSub: 'المفاهيم × الإشارات', understood: 'فهم', struggling: 'صعوبة', misconception: 'فكرة خاطئة', mastery: 'الإتقان', subjects: 'متوسط الإتقان حسب المادة', empty: 'لا توجد بيانات بعد. اسأل المعلّم وأجب عن أسئلته وسيظهر تقدّمك هنا.', guest: 'سجّل الدخول لحفظ تقدّمك.', note: 'محسوب من تبادلاتك. لا توقعات ولا علامات مخترعة. حالة المفهوم تحتاج إشارتين على الأقل.', legendLow: 'إشارات قليلة', legendHigh: 'كثيرة', error: 'تعذّر تحميل التقدّم.' },
}
const STATUS_STYLE = { mastered: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400', in_progress: 'bg-sky-500/15 text-sky-600 dark:text-sky-400', to_review: 'bg-amber-500/15 text-amber-600 dark:text-amber-400' }
// one hue per signal; the intensity grows with the count
const HEAT = { understood: '16, 185, 129', struggling: '245, 158, 11', misconception: '124, 77, 255' } as const

export function ProgressView({ lang }: { lang: Lang }) {
  const c = C[lang]
  const [data, setData] = useState<Progress | null>(null)
  const [error, setError] = useState('')
  const signedIn = typeof window !== 'undefined' && !!savedSession()

  useEffect(() => {
    if (!savedSession()) return
    fetch(`/engine/students/me/progress?lang=${lang}`, { headers: authHeader(), cache: 'no-store' })
      .then(async (r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return (await r.json()) as Progress })
      .then(setData)
      .catch((e: Error) => setError(`${c.error} (${e.message})`))
  }, [lang]) // eslint-disable-line react-hooks/exhaustive-deps

  const concepts = useMemo(() => (data?.concepts ?? []).slice(0, 12), [data])
  const maxCount = useMemo(() => Math.max(1, ...concepts.flatMap((x) => [x.understood, x.struggling, x.misconception])), [concepts])
  const subjects = Object.entries(data?.by_subject ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <section aria-labelledby="progress-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2 rounded-[2rem] border border-border bg-gradient-to-br from-primary/15 via-card to-brand-cyan/10 p-6 shadow-sm sm:p-8">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-secondary text-primary"><BarChart3 className="size-6" aria-hidden="true" /></span>
        <h1 id="progress-title" className="text-3xl font-bold tracking-tight text-foreground">{c.title}</h1>
        <p className="max-w-2xl text-muted-foreground">{c.intro}</p>
      </div>

      {!signedIn ? <p className="rounded-2xl border border-border bg-card p-6 text-muted-foreground">{c.guest}</p> : null}
      {error ? <p role="alert" className="rounded-2xl bg-destructive/10 p-4 text-sm text-destructive">{error}</p> : null}
      {signedIn && !data && !error ? <div className="flex justify-center py-16 text-muted-foreground"><LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" /></div> : null}

      {data ? (
        <>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
            <div className="flex flex-col gap-3 rounded-3xl border border-border bg-card p-6 shadow-sm">
              <span className="flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/25 to-brand-cyan/25 text-primary shadow-inner"><Sparkles className="size-6" aria-hidden="true" /></span>
              <h2 className="text-xl font-bold text-foreground">{c.insight}</h2>
              <p className="border-s-2 border-primary/40 ps-3 leading-relaxed text-muted-foreground">{data.insight}</p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-5">
              {(['mastered', 'in_progress', 'to_review'] as const).map((k) => (
                <div key={k} className="flex flex-col justify-between gap-2 rounded-3xl border border-border bg-card p-4 shadow-sm">
                  <span className={cn('inline-flex w-fit items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold', STATUS_STYLE[k])}>
                    {k === 'mastered' ? <CheckCircle2 className="size-3.5" /> : k === 'to_review' ? <AlertTriangle className="size-3.5" /> : <Target className="size-3.5" />}{c[k]}
                  </span>
                  <span className="text-3xl font-bold tabular-nums text-foreground">{data.counts[k] ?? 0}</span>
                </div>
              ))}
              <div className="flex flex-col justify-between gap-2 rounded-3xl border border-border bg-card p-4 shadow-sm">
                <span className="inline-flex items-center gap-1 text-xs font-bold text-muted-foreground"><Clock3 className="size-3.5" />{c.sessions}</span>
                <span className="text-3xl font-bold tabular-nums text-foreground">{data.sessions}</span>
              </div>
              <div className="flex flex-col justify-between gap-2 rounded-3xl border border-border bg-card p-4 shadow-sm">
                <span className="inline-flex items-center gap-1 text-xs font-bold text-muted-foreground"><MessageSquare className="size-3.5" />{c.messages}</span>
                <span className="text-3xl font-bold tabular-nums text-foreground">{data.messages}</span>
              </div>
            </div>
          </div>

          {concepts.length === 0 ? (
            <p className="rounded-3xl border border-dashed border-border bg-card p-8 text-center text-muted-foreground">{c.empty}</p>
          ) : (
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <div className="overflow-x-auto rounded-3xl border border-border bg-card p-6 shadow-sm">
                <h2 className="text-xl font-bold text-foreground">{c.heat}</h2>
                <p className="text-sm text-muted-foreground">{c.heatSub}</p>
                <table className="mt-5 w-full min-w-[34rem] border-separate border-spacing-1.5 text-sm">
                  <thead>
                    <tr className="text-xs font-semibold text-muted-foreground">
                      <th className="text-start font-semibold" />
                      {(['understood', 'struggling', 'misconception'] as const).map((k) => <th key={k} className="px-2 font-semibold">{c[k]}</th>)}
                      <th className="px-2 font-semibold">{c.mastery}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {concepts.map((x) => (
                      <tr key={x.concept}>
                        <th scope="row" className="max-w-[14rem] pe-2 text-start font-semibold text-foreground">
                          <span className="block truncate" title={x.last_note || x.concept}>{x.concept}</span>
                          <span className={cn('mt-0.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-bold', STATUS_STYLE[x.status])}>{c[x.status]}</span>
                        </th>
                        {(['understood', 'struggling', 'misconception'] as const).map((k) => (
                          <td key={k} className="h-12 rounded-xl text-center font-bold tabular-nums text-foreground"
                            style={{ background: `rgba(${HEAT[k]}, ${x[k] ? 0.15 + 0.7 * (x[k] / maxCount) : 0.04})` }}>
                            {x[k] || ''}
                          </td>
                        ))}
                        <td className="w-32 px-2">
                          <div className="h-2.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-gradient-to-r from-primary to-brand-cyan" style={{ width: `${Math.round(x.mastery * 100)}%` }} /></div>
                          <span className="text-xs tabular-nums text-muted-foreground">{Math.round(x.mastery * 100)} %</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{c.legendLow}</span><span className="h-2 w-40 rounded-full bg-gradient-to-r from-primary/10 via-primary/50 to-primary" /><span>{c.legendHigh}</span>
                </div>
              </div>

              <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
                <h2 className="text-xl font-bold text-foreground">{c.subjects}</h2>
                <div className="mt-6 flex h-56 items-end gap-4 border-b border-s border-border ps-3">
                  {subjects.map(([s, v], i) => (
                    <div key={s} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
                      <span className="text-xs font-bold tabular-nums text-foreground">{Math.round(v * 100)} %</span>
                      <div className={cn('w-full max-w-14 rounded-t-xl bg-gradient-to-t', i % 3 === 0 ? 'from-primary-deep to-primary' : i % 3 === 1 ? 'from-sky-600 to-brand-cyan' : 'from-violet-600 to-violet-400')} style={{ height: `${Math.max(4, v * 100)}%` }} />
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex gap-4 ps-3">
                  {subjects.map(([s]) => <span key={s} className="flex-1 truncate text-center text-xs font-semibold capitalize text-muted-foreground">{s}</span>)}
                </div>
              </div>
            </div>
          )}
          <p className="flex items-start gap-2 rounded-2xl border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground"><Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />{c.note}</p>
        </>
      ) : null}
    </section>
  )
}
