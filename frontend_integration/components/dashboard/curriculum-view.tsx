'use client'

// "Programme" view: the maths programme by level, from the TRACE engine (GET /api/v1/curriculum?level=).
// The data is an INDICATIVE reference written by the TRACE team, not the official Ministry document: the engine sends
// a disclaimer and this view always shows it.
import { useEffect, useMemo, useState } from 'react'
import { BookMarked, ChevronDown, ChevronRight, Info, LoaderCircle, Ruler, Search, Shapes, Sigma, BarChart3, TrendingUp } from 'lucide-react'
import { ChapterDetailView } from './ChapterDetailView'
import type { Lang } from '@/lib/translations'
import { cn } from '@/lib/utils'

type Tri = Record<string, string>
type Chapter = { id: string; domain: string; title: Tri; notions: string[] }
type Level = { id: string; cycle: string; name: Tri; chapters: Chapter[] }
type Cycle = { name: Tri; aliases: string[]; resource: { name: string; url: string } }
type Curriculum = { status: string; disclaimer: Tri; domains: Record<string, Tri>; levels: Level[]; level: Level | null; cycles: Record<string, Cycle> }

const COPY: Record<Lang, Record<string, string>> = {
  en: { title: 'Programme', intro: 'The maths chapters of each level, from primary school to the Bac.', cycle: 'Cycle', search: 'Search: “School”, “Collège”, “Lycée” or a chapter', open: 'Open the chapter', noMatch: 'No chapter matches this search.', level: 'Level', base: 'Basic education', secondary: 'Secondary', chapters: 'chapters', chapter: 'Chapter', all: 'All', error: 'The programme could not be loaded.', notions: 'Key notions' },
  fr: { title: 'Programme', intro: 'Les chapitres de maths de chaque niveau, du primaire au Bac.', cycle: 'Cycle', search: 'Rechercher : « School », « Collège », « Lycée » ou un chapitre', open: 'Ouvrir le chapitre', noMatch: 'Aucun chapitre ne correspond à cette recherche.', level: 'Niveau', base: 'Enseignement de base', secondary: 'Secondaire', chapters: 'chapitres', chapter: 'Chapitre', all: 'Tous', error: 'Le programme n’a pas pu être chargé.', notions: 'Notions clés' },
  ar: { title: 'البرنامج', intro: 'فصول الرياضيات لكل مستوى، من الابتدائي إلى الباكالوريا.', cycle: 'المرحلة', search: 'ابحث: ابتدائي، إعدادي، ثانوي أو فصل', open: 'افتح الفصل', noMatch: 'لا يوجد فصل يطابق هذا البحث.', level: 'المستوى', base: 'التعليم الأساسي', secondary: 'التعليم الثانوي', chapters: 'فصول', chapter: 'الفصل', all: 'الكل', error: 'تعذّر تحميل البرنامج.', notions: 'المفاهيم الأساسية' },
}
const ICONS: Record<string, typeof Sigma> = { algebre: Sigma, analyse: TrendingUp, geometrie: Shapes, statistiques: BarChart3, mesures: Ruler }
const fold = (x: string) => x.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim()
const CYCLE_OF_LEVEL = (id: string) => (id.endsWith('p') ? 'primaire' : ['7e', '8e', '9e'].includes(id) ? 'college' : 'lycee')
const KEY = 'trace.curriculum.level'

export function CurriculumView({ lang }: { lang: Lang }) {
  const c = COPY[lang]
  const pick = (t?: Tri) => (t ? t[lang] || t.fr : '')
  const [data, setData] = useState<Curriculum | null>(null)
  const [level, setLevel] = useState<string>('9e')
  useEffect(() => {
    try { const saved = window.localStorage.getItem(KEY); if (saved) setLevel(saved) } catch { /* storage unavailable */ }
  }, [])
  const [domain, setDomain] = useState<string>('all')
  const [cycle, setCycle] = useState<string>(() => CYCLE_OF_LEVEL('9e'))
  const [query, setQuery] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    setError('')
    fetch(`/engine/curriculum?level=${encodeURIComponent(level)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return (await r.json()) as Curriculum
      })
      .then((d) => { if (live) setData(d) })
      .catch((e: Error) => { if (live) setError(`${c.error} (${e.message})`) })
      .finally(() => { if (live) setLoading(false) })
    try { window.localStorage.setItem(KEY, level) } catch { /* storage unavailable */ }
    return () => { live = false }
  }, [level]) // eslint-disable-line react-hooks/exhaustive-deps

  // typing a cycle name ("School", "Collège", "Lycée", "ابتدائي"...) switches the cycle; anything else filters chapters
  const cycleTyped = useMemo(() => {
    const q = fold(query)
    if (!q || !data?.cycles) return null
    return Object.entries(data.cycles).find(([id, cy]) => fold(id) === q || cy.aliases.some((a) => fold(a) === q) || Object.values(cy.name).some((n) => fold(n) === q))?.[0] ?? null
  }, [query, data])
  useEffect(() => { if (cycleTyped && cycleTyped !== cycle) chooseCycle(cycleTyped) }, [cycleTyped]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setCycle(CYCLE_OF_LEVEL(level)) }, [level])
  function chooseCycle(cy: string) {
    setCycle(cy)
    const first = data?.levels.find((lv) => lv.cycle === cy)
    if (first && CYCLE_OF_LEVEL(level) !== cy) { setLevel(first.id); setDomain('all') }
  }
  const textFilter = cycleTyped ? '' : fold(query)
  const chapters = useMemo(() => (data?.level?.chapters ?? []).filter((ch) => (domain === 'all' || ch.domain === domain)
    && (!textFilter || fold(Object.values(ch.title).join(' ') + ' ' + ch.notions.join(' ')).includes(textFilter))), [data, domain, textFilter])
  const domainsHere = useMemo(() => Array.from(new Set((data?.level?.chapters ?? []).map((ch) => ch.domain))), [data])
  const cycleIds = data?.cycles ? Object.keys(data.cycles) : ['primaire', 'college', 'lycee']

  if (openId) return <ChapterDetailView chapterId={openId} lang={lang} onBack={() => setOpenId(null)} />

  return (
    <section aria-labelledby="curriculum-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 rounded-[2rem] border border-border bg-gradient-to-br from-accent via-card to-secondary/70 p-6 shadow-sm sm:flex-row sm:items-end sm:justify-between sm:p-8">
        <div className="flex flex-col gap-2">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-secondary text-primary"><BookMarked className="size-6" aria-hidden="true" /></span>
          <h1 id="curriculum-title" className="text-3xl font-bold tracking-tight text-foreground">{c.title}</h1>
          <p className="max-w-xl text-muted-foreground">{c.intro}</p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="flex min-w-44 flex-col gap-2 text-sm font-semibold text-foreground">
            {c.cycle}
            <span className="relative">
              <select value={cycle} onChange={(e) => { setQuery(''); chooseCycle(e.target.value) }} className="h-12 w-full appearance-none rounded-2xl border border-input bg-background ps-4 pe-10 text-base font-semibold outline-none focus:border-primary focus:ring-2 focus:ring-primary/25">
                {cycleIds.map((id) => <option key={id} value={id}>{data?.cycles ? pick(data.cycles[id].name) : id}</option>)}
              </select>
              <ChevronDown className="pointer-events-none absolute end-4 top-1/2 size-4 -translate-y-1/2" aria-hidden="true" />
            </span>
          </label>
          <label className="flex min-w-56 flex-col gap-2 text-sm font-semibold text-foreground">
            {c.level}
            <span className="relative">
              <select value={level} onChange={(e) => { setLevel(e.target.value); setDomain('all') }} className="h-12 w-full appearance-none rounded-2xl border border-input bg-background ps-4 pe-10 text-base font-semibold outline-none focus:border-primary focus:ring-2 focus:ring-primary/25">
                {data
                  ? data.levels.filter((lv) => lv.cycle === cycle).map((lv) => <option key={lv.id} value={lv.id}>{pick(lv.name)}</option>)
                  : <option value={level}>{level}</option>}
              </select>
              <ChevronDown className="pointer-events-none absolute end-4 top-1/2 size-4 -translate-y-1/2" aria-hidden="true" />
            </span>
          </label>
        </div>
      </div>

      <label className="relative block">
        <span className="sr-only">{c.search}</span>
        <Search className="pointer-events-none absolute start-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={c.search} className="h-12 w-full rounded-2xl border border-input bg-card ps-11 pe-4 text-base outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/25" />
      </label>

      {data ? (
        <p className="flex items-start gap-2 rounded-2xl border border-border bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />{pick(data.disclaimer)}
        </p>
      ) : null}

      {error ? <p role="alert" className="rounded-2xl bg-destructive/10 p-4 text-sm text-destructive">{error}</p> : null}

      {data?.level ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-bold text-foreground">{pick(data.level.name)} <span className="text-base font-normal text-muted-foreground">· {data.level.chapters.length} {c.chapters}</span></h2>
            <div className="flex flex-wrap gap-2" role="group" aria-label={c.chapters}>
              {['all', ...domainsHere].map((d) => (
                <button key={d} type="button" aria-pressed={domain === d} onClick={() => setDomain(d)} className={cn('min-h-9 rounded-full border px-3 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', domain === d ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-foreground hover:border-primary/50')}>
                  {d === 'all' ? c.all : pick(data.domains[d])}
                </button>
              ))}
            </div>
          </div>
          <ol className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-3', loading && 'opacity-60')}>
            {chapters.map((ch) => {
              const Icon = ICONS[ch.domain] ?? Sigma
              const n = data.level!.chapters.indexOf(ch) + 1
              return (
                <li key={ch.id}>
                <button type="button" onClick={() => setOpenId(ch.id)} aria-label={`${c.open} : ${pick(ch.title)}`} className="flex h-full w-full flex-col gap-3 rounded-3xl border border-border bg-card p-5 text-start shadow-sm transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex size-11 items-center justify-center rounded-2xl bg-secondary text-primary"><Icon className="size-5" aria-hidden="true" /></span>
                    <span className="rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground">{c.chapter} {n}</span>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-primary">{pick(data.domains[ch.domain])}</p>
                    <h3 className="mt-1 text-lg font-bold leading-snug text-foreground">{pick(ch.title)}</h3>
                  </div>
                  {ch.notions.length ? (
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground">{c.notions}</p>
                      <ul className="mt-1.5 flex flex-wrap gap-1.5" lang="fr" dir="ltr">
                        {ch.notions.map((x) => <li key={x} className="rounded-full border border-border bg-background/70 px-2.5 py-1 text-xs text-foreground">{x}</li>)}
                      </ul>
                    </div>
                  ) : null}
                  <span className="mt-auto inline-flex items-center gap-1 text-sm font-semibold text-primary">{c.open}<ChevronRight className="size-4 rtl:rotate-180" aria-hidden="true" /></span>
                </button>
                </li>
              )
            })}
          </ol>
          {!chapters.length ? <p className="rounded-2xl border border-dashed border-border p-6 text-center text-muted-foreground">{c.noMatch}</p> : null}
        </>
      ) : loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground"><LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" /></div>
      ) : null}
    </section>
  )
}
