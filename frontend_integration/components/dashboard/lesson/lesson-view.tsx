'use client'

// "Transformer en manuel 3D" now opens this interactive lesson (it replaces the old page-turning 3D book).
// - The demo fractions course (a document about fractions / relative numbers) -> FractionsLesson: hand-built
//   interactions from the course pages, 3D fraction cake, results and answer keys computed by code, works offline.
// - Any other PDF or tutor explanation -> GenericLesson: the same A-G layout filled with the engine's checked lessons
//   (keys on the server). A fractions lesson is never shown for another subject.
import { useCallback, useEffect, useState } from 'react'
import { MotionConfig, motion, useReducedMotion, useScroll, useSpring } from 'motion/react'
import { X } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { cn } from '@/lib/utils'
import { FRACTION_SECTIONS, FractionsLesson } from './fractions-lesson'
import { GenericLesson } from './generic-lesson'

type Source = { docId?: string; text?: string; name?: string }
type Nav = { id: string; letter: string; title: string }

const EXIT = { fr: 'Quitter la leçon', en: 'Exit the lesson', ar: 'الخروج من الدرس' }
const ACTIVITIES = { fr: 'activités', en: 'activities', ar: 'أنشطة' }

export const isFractionsCourse = (s: Source) => /fraction|relatif/i.test(s.name ?? '')

export function LessonView({ lang, source, onExit }: { lang: Lang; source: Source; onExit: () => void }) {
  const reduced = useReducedMotion() ?? false
  const fractions = isFractionsCourse(source)
  const [title, setTitle] = useState(fractions ? 'Fractions et nombres relatifs' : '')
  const [nav, setNav] = useState<Nav[]>(fractions ? FRACTION_SECTIONS.map((s) => ({ ...s })) : [])
  const [done, setDone] = useState(0)
  const [total, setTotal] = useState(fractions ? 7 : 0)
  const [active, setActive] = useState(nav[0]?.id ?? '')
  const [scroller, setScroller] = useState<HTMLElement | null>(null)
  const { scrollYProgress } = useScroll({ container: scroller ? { current: scroller } : undefined })
  const bar = useSpring(scrollYProgress, { stiffness: 120, damping: 24 })

  // which section is on screen (for the nav)
  useEffect(() => {
    if (!scroller || !nav.length) return
    const io = new IntersectionObserver((entries) => {
      const v = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
      if (v) setActive(v.target.id.replace('lesson-', ''))
    }, { root: scroller, rootMargin: '-20% 0px -60% 0px' })
    nav.forEach((n) => { const el = document.getElementById(`lesson-${n.id}`); if (el) io.observe(el) })
    return () => io.disconnect()
  }, [scroller, nav])

  const onFractions = useCallback((d: Set<string>) => setDone(d.size), [])
  const onGeneric = useCallback((t: string, sections: Nav[], dn: number, tot: number) => { setTitle(t); setNav(sections); setDone(dn); setTotal(tot) }, [])

  return (
    <MotionConfig reducedMotion="user">
      <section className="fixed inset-0 z-50 flex flex-col bg-background text-foreground" aria-label={title || 'Leçon interactive'}>
        <header className="z-10 border-b border-border bg-background/90 backdrop-blur">
          <div className="flex items-center gap-3 px-4 py-3">
            <button type="button" onClick={onExit} className="inline-flex min-h-10 items-center gap-2 rounded-full bg-muted px-3 text-sm font-semibold hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><X className="size-4" />{EXIT[lang]}</button>
            <span className="min-w-0 truncate font-bold">{title}</span>
            {total ? <span className="ms-auto shrink-0 rounded-full bg-secondary px-3 py-1 text-xs font-bold text-primary-deep">{done} / {total} {ACTIVITIES[lang]}</span> : null}
          </div>
          {nav.length ? (
            <nav aria-label="Sections" className="flex gap-1.5 overflow-x-auto px-4 pb-3">
              {nav.map((n) => (
                <button key={n.id} type="button" onClick={() => document.getElementById(`lesson-${n.id}`)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })}
                  aria-current={active === n.id ? 'true' : undefined}
                  className={cn('inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold transition', active === n.id ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-foreground hover:border-primary/50')}>
                  <span className="opacity-80">{n.letter}</span><span className="max-w-40 truncate">{n.title}</span>
                </button>
              ))}
            </nav>
          ) : null}
          <motion.div className="h-1 origin-left bg-gradient-to-r from-primary to-brand-cyan rtl:origin-right" style={{ scaleX: bar }} />
        </header>
        <div ref={setScroller} className="min-h-0 flex-1 overflow-y-auto">
          {fractions
            ? <FractionsLesson reduced={reduced} onProgress={onFractions} />
            : <GenericLesson lang={lang === 'ar' || lang === 'en' ? lang : 'fr'} source={source} onProgress={onGeneric} />}
        </div>
      </section>
    </MotionConfig>
  )
}
