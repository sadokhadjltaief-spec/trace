'use client'

// "Images & videos": the student asks for an educational diagram or a short narrated video.
// Diagrams are drawn by the TRACE engine with computed values (never AI-generated pixels); videos are slides with
// those diagrams + a narration (online neural voice, offline Windows voice) whose texts passed the guards.
import { useState } from 'react'
import { Clapperboard, ImageIcon, LoaderCircle, Sparkles, Wand2 } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { authHeader } from '@/lib/auth'
import { cn } from '@/lib/utils'

type Media = { type: 'image' | 'video'; ok: boolean; url: string | null; title: string | null; caption: string | null; error: string | null; duration_s?: number | null; subtitles_url?: string | null }
type Item = { id: number; kind: 'image' | 'video'; request: string; media: Media | null; error: string }

const C: Record<Lang, Record<string, string>> = {
  fr: { title: 'Images & vidéos', intro: 'Demande un schéma ou une courte vidéo expliquée pour comprendre une notion.', placeholder: 'Ex. : la parabole y = x² − 4x + 3 avec ses racines, le théorème de Pythagore, les fractions 1/3 et 2/5…', image: 'Créer une image', video: 'Créer une vidéo', working: 'Création en cours…', workingVideo: 'La vidéo prend environ une minute (diapos, voix, montage).', note: 'Les schémas sont dessinés par le calcul (valeurs vérifiées), pas inventés par une IA d’images. Les textes des vidéos passent les vérifications.', ideas: 'Idées', s: 's', error: 'La création a échoué.' },
  en: { title: 'Images & videos', intro: 'Ask for a diagram or a short narrated video to understand a notion.', placeholder: 'E.g. the parabola y = x² − 4x + 3 with its roots, the Pythagorean theorem, the fractions 1/3 and 2/5…', image: 'Create an image', video: 'Create a video', working: 'Creating…', workingVideo: 'A video takes about a minute (slides, voice, editing).', note: 'Diagrams are drawn by computation (checked values), not invented by an image AI. Video texts pass the checks.', ideas: 'Ideas', s: 's', error: 'Creation failed.' },
  ar: { title: 'صور وفيديوهات', intro: 'اطلب مخططًا أو فيديو قصيرًا مشروحًا لفهم مفهوم.', placeholder: 'مثال: القطع المكافئ y = x² − 4x + 3 وجذوره، مبرهنة فيثاغورس، الكسران 1/3 و2/5…', image: 'أنشئ صورة', video: 'أنشئ فيديو', working: 'جارٍ الإنشاء…', workingVideo: 'يستغرق الفيديو دقيقة تقريبًا.', note: 'المخططات تُرسم بالحساب (قيم مُتحقَّق منها) ولا يخترعها ذكاء اصطناعي للصور.', ideas: 'أفكار', s: 'ث', error: 'فشل الإنشاء.' },
}
const IDEAS: Record<Lang, string[]> = {
  fr: ['La parabole y = x² − 4x + 3 et ses racines', 'Comparer 1/3 et 2/5 avec des barres', 'Le théorème de Pythagore avec un triangle 3-4-5', 'Les étapes pour résoudre une équation du second degré'],
  en: ['The parabola y = x² − 4x + 3 and its roots', 'Compare 1/3 and 2/5 with bars', 'The Pythagorean theorem with a 3-4-5 triangle', 'Steps to solve a quadratic equation'],
  ar: ['القطع المكافئ y = x² − 4x + 3 وجذوره', 'قارن 1/3 و2/5 بالأشرطة', 'مبرهنة فيثاغورس بمثلث 3-4-5', 'خطوات حل معادلة من الدرجة الثانية'],
}

export function MediaStudio({ lang }: { lang: Lang }) {
  const c = C[lang]
  const [request, setRequest] = useState('')
  const [items, setItems] = useState<Item[]>([])
  const busy = items.some((x) => !x.media && !x.error)

  async function create(kind: 'image' | 'video') {
    const text = request.trim()
    if (!text || busy) return
    const id = Date.now()
    setItems((xs) => [{ id, kind, request: text, media: null, error: '' }, ...xs])
    try {
      const r = await fetch(`/api/media/${kind}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeader() }, body: JSON.stringify({ request: text, lang }) })
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${r.status}`)
      setItems((xs) => xs.map((x) => (x.id === id ? { ...x, media: data as Media, error: (data as Media).ok ? '' : (data as Media).error ?? c.error } : x)))
    } catch (e) {
      setItems((xs) => xs.map((x) => (x.id === id ? { ...x, error: `${c.error} (${(e as Error).message})` } : x)))
    }
  }

  return (
    <section aria-labelledby="media-title" className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 rounded-[2rem] border border-border bg-gradient-to-br from-primary/15 via-card to-violet-500/10 p-6 shadow-sm sm:p-8">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-secondary text-primary"><Wand2 className="size-6" aria-hidden="true" /></span>
        <h1 id="media-title" className="text-3xl font-bold tracking-tight text-foreground">{c.title}</h1>
        <p className="max-w-2xl text-muted-foreground">{c.intro}</p>
        <textarea value={request} onChange={(e) => setRequest(e.target.value)} rows={3} placeholder={c.placeholder} className="w-full resize-y rounded-2xl border border-input bg-background px-4 py-3 text-base outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/25" />
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground"><Sparkles className="size-3.5" />{c.ideas}</span>
          {IDEAS[lang].map((x) => (
            <button key={x} type="button" onClick={() => setRequest(x)} className="rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground transition hover:border-primary/50 hover:text-primary">{x}</button>
          ))}
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <button type="button" disabled={!request.trim() || busy} onClick={() => create('image')} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 font-semibold text-primary-foreground transition hover:bg-primary-deep disabled:opacity-50"><ImageIcon className="size-4" />{c.image}</button>
          <button type="button" disabled={!request.trim() || busy} onClick={() => create('video')} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-border bg-card px-5 font-semibold text-foreground transition hover:bg-muted disabled:opacity-50"><Clapperboard className="size-4" />{c.video}</button>
        </div>
      </div>

      <ul className="grid gap-5 lg:grid-cols-2">
        {items.map((x) => (
          <li key={x.id} className="flex flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-sm">
            <div className={cn('flex items-center gap-2 border-b border-border px-5 py-3 text-sm font-semibold', x.kind === 'video' ? 'text-violet-500' : 'text-primary')}>
              {x.kind === 'video' ? <Clapperboard className="size-4" /> : <ImageIcon className="size-4" />}
              <span className="truncate text-foreground">{x.media?.title || x.request}</span>
              {x.media?.duration_s ? <span className="ms-auto text-xs tabular-nums text-muted-foreground">{Math.round(x.media.duration_s)} {c.s}</span> : null}
            </div>
            {!x.media && !x.error ? (
              <div className="flex flex-col items-center gap-2 p-10 text-center text-muted-foreground">
                <LoaderCircle className="size-6 animate-spin motion-reduce:animate-none text-primary" />
                <p className="font-semibold text-foreground">{c.working}</p>
                {x.kind === 'video' ? <p className="text-sm">{c.workingVideo}</p> : null}
              </div>
            ) : x.error ? (
              <p role="alert" className="p-5 text-sm text-destructive">{x.error}</p>
            ) : x.media?.type === 'video' && x.media.url ? (
              <video controls preload="metadata" className="aspect-video w-full bg-black" src={x.media.url}>
                {x.media.subtitles_url ? <track kind="subtitles" src={x.media.subtitles_url} default /> : null}
              </video>
            ) : x.media?.url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <a href={x.media.url} target="_blank" rel="noreferrer" className="bg-white"><img src={x.media.url} alt={x.media.title ?? ''} className="w-full" /></a>
            ) : null}
            {x.media?.caption ? <p className="px-5 py-3 text-sm text-muted-foreground">{x.media.caption}</p> : null}
          </li>
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">{c.note}</p>
    </section>
  )
}
