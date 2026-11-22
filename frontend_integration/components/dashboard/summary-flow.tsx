'use client'

import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpenText, Check, ChevronDown, FileText, FileUp, Focus, Languages, LoaderCircle, Sparkles, TextQuote, Upload, X } from 'lucide-react'
import { siWikipedia, siYoutube } from 'simple-icons'
import type { Lang } from '@/lib/translations'

type Props = { lang: Lang; onBack: () => void }
type SourceKind = 'file' | 'text' | 'youtube' | 'wikipedia'
type Stage = 'landing' | 'material' | 'settings' | 'loading' | 'complete'

const COPY: Record<Lang, {
  back: string; create: string; eyebrow: string; headline: string; intro: string; benefit: string; source: string; sourceIntro: string; upload: string; paste: string; youtube: string; wikipedia: string; fileHint: string; textLabel: string; linkLabel: string; continue: string; pages: string; focus: string; focusHint: string; focusIdeas: string[]; language: string; english: string; french: string; arabic: string; start: string; working: string; workingText: string; ready: string; readyText: string; selected: string; stepMaterial: string; stepSettings: string; stepSummary: string; chooseFile: string; pageUnit: string; sectionTitle: string; wizardTitle: string; close: string; remove: string; progressLabel: string
}> = {
  en: { back: 'Home', create: 'Create a summary', eyebrow: 'A little more clarity', headline: 'The big ideas, without the extra pages.', intro: 'Turn a long read into a calm, clear overview you can come back to whenever you need it.', benefit: 'Keep the important bits close. Your summary can become a starting point for what to explore next.', source: 'Start with your material', sourceIntro: 'Choose a file, a passage, or a source on the web.', upload: 'Upload a file', paste: 'Paste text', youtube: 'YouTube video', wikipedia: 'Wikipedia article', fileHint: 'Drop a PDF, Word document, or text file here, or browse.', textLabel: 'Your text', linkLabel: 'Source link or article title', continue: 'Continue to settings', pages: 'Summary length', focus: 'What should stand out?', focusHint: 'For example: the main argument, a process, or the practical takeaways.', focusIdeas: ['Main ideas', 'Useful examples', 'Key takeaways'], language: 'Write the summary in', english: 'English', french: 'French', arabic: 'Arabic', start: 'Create summary', working: 'Gathering the important threads…', workingText: 'We’re arranging the source into a clear, easy-to-scan overview.', ready: 'Your summary workspace is ready', readyText: 'Your selected material is ready to be summarized.', selected: 'Selected material', stepMaterial: 'Material', stepSettings: 'Settings', stepSummary: 'Summary', chooseFile: 'Choose a file', pageUnit: 'pages', sectionTitle: 'Summarize', wizardTitle: 'Create summary', close: 'Close summary', remove: 'Remove selected material', progressLabel: 'Summary creation progress' },
  fr: { back: 'Accueil', create: 'Créer un résumé', eyebrow: 'Un peu plus de clarté', headline: 'L’essentiel, sans les pages en trop.', intro: 'Transforme un long texte en aperçu clair et agréable à retrouver dès que tu en as besoin.', benefit: 'Garde les idées importantes à portée de main et découvre facilement la suite.', source: 'Commence avec ton contenu', sourceIntro: 'Choisis un fichier, un passage ou une source sur le web.', upload: 'Importer un fichier', paste: 'Coller du texte', youtube: 'Vidéo YouTube', wikipedia: 'Article Wikipédia', fileHint: 'Dépose un PDF, un document Word ou un fichier texte, ou parcours tes fichiers.', textLabel: 'Ton texte', linkLabel: 'Lien source ou titre de l’article', continue: 'Continuer vers les réglages', pages: 'Longueur du résumé', focus: 'Sur quoi mettre l’accent ?', focusHint: 'Par exemple : l’argument principal, un processus ou les conseils pratiques.', focusIdeas: ['Idées principales', 'Exemples utiles', 'À retenir'], language: 'Rédiger le résumé en', english: 'Anglais', french: 'Français', arabic: 'Arabe', start: 'Créer le résumé', working: 'Nous rassemblons les idées importantes…', workingText: 'Nous organisons la source en un aperçu clair et facile à parcourir.', ready: 'Ton espace de résumé est prêt', readyText: 'Le contenu choisi est prêt à être résumé.', selected: 'Contenu sélectionné', stepMaterial: 'Contenu', stepSettings: 'Réglages', stepSummary: 'Résumé', chooseFile: 'Choisir un fichier', pageUnit: 'pages', sectionTitle: 'Résumer', wizardTitle: 'Créer un résumé', close: 'Fermer le résumé', remove: 'Supprimer le contenu', progressLabel: 'Progression de la création du résumé' },
  ar: { back: 'الرئيسية', create: 'أنشئ ملخصًا', eyebrow: 'مزيد من الوضوح', headline: 'الأفكار الأهم، بلا صفحات إضافية.', intro: 'حوّل النص الطويل إلى نظرة واضحة ومريحة يمكنك العودة إليها متى احتجت.', benefit: 'احتفظ بالأفكار المهمة قريبة، واجعل الملخص نقطة بداية لاكتشاف المزيد.', source: 'ابدأ بالمادة', sourceIntro: 'اختر ملفًا أو مقطعًا أو مصدرًا من الويب.', upload: 'ارفع ملفًا', paste: 'الصق نصًا', youtube: 'فيديو يوتيوب', wikipedia: 'مقالة ويكيبيديا', fileHint: 'أفلت ملف PDF أو Word أو نص هنا، أو تصفح ملفاتك.', textLabel: 'النص', linkLabel: 'رابط المصدر أو عنوان المقالة', continue: 'المتابعة إلى الإعدادات', pages: 'طول الملخص', focus: 'ما الذي تريد إبرازه؟', focusHint: 'مثلًا: الفكرة الرئيسية أو الخطوات أو الفوائد العملية.', focusIdeas: ['الأفكار الرئيسية', 'أمثلة مفيدة', 'أهم النقاط'], language: 'لغة الملخص', english: 'الإنجليزية', french: 'الفرنسية', arabic: 'العربية', start: 'أنشئ الملخص', working: 'نجمع الخيوط المهمة…', workingText: 'نرتب المصدر في نظرة واضحة وسهلة القراءة.', ready: 'مساحة الملخص جاهزة', readyText: 'المادة التي اخترتها جاهزة للتلخيص.', selected: 'المادة المحددة', stepMaterial: 'المادة', stepSettings: 'الإعدادات', stepSummary: 'الملخص', chooseFile: 'اختر ملفًا', pageUnit: 'صفحات', sectionTitle: 'تلخيص', wizardTitle: 'أنشئ ملخصًا', close: 'إغلاق الملخص', remove: 'إزالة المادة المحددة', progressLabel: 'تقدم إنشاء الملخص' },
}

const SOURCE_ICONS = { file: FileUp, text: TextQuote, youtube: null, wikipedia: null }

export function SummaryFlow({ lang, onBack }: Props) {
  const text = COPY[lang]
  const [stage, setStage] = useState<Stage>('landing')
  const [source, setSource] = useState<SourceKind | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [value, setValue] = useState('')
  const [pages, setPages] = useState(2)
  const [focus, setFocus] = useState('')
  const [language, setLanguage] = useState<Lang>(lang)
  const [progress, setProgress] = useState(0)
  const [dragging, setDragging] = useState(false)

  useEffect(() => {
    if (stage !== 'loading') return
    const startedAt = Date.now()
    const timer = window.setInterval(() => {
      const next = Math.min(100, Math.round(((Date.now() - startedAt) / 4400) * 100))
      setProgress(next)
      if (next === 100) setStage('complete')
    }, 100)
    return () => window.clearInterval(timer)
  }, [stage])

  const chooseSource = (next: SourceKind) => {
    setSource(next)
    setValue('')
    setFile(null)
  }

  const sourceIsReady = source === 'file' ? Boolean(file) : Boolean(value.trim())
  const selectedName = file?.name ?? (source === 'youtube' ? 'YouTube video' : source === 'wikipedia' ? 'Wikipedia article' : 'Pasted text')

  function acceptFile(next: File | undefined) {
    if (!next) return
    setFile(next)
    setSource('file')
    setStage('settings')
  }

  function handleHeaderBack() {
    if (stage === 'landing' || stage === 'loading' || stage === 'complete') onBack()
    else setStage(stage === 'settings' ? 'material' : 'landing')
  }

  const headerBackLabel = stage === 'material' ? text.sectionTitle : stage === 'settings' ? text.stepMaterial : text.back

  const sources: { id: SourceKind; title: string }[] = [
    { id: 'file', title: text.upload }, { id: 'text', title: text.paste }, { id: 'youtube', title: text.youtube }, { id: 'wikipedia', title: text.wikipedia },
  ]

  return (
    <section className="min-h-dvh bg-background text-foreground" lang={lang} dir={lang === 'ar' ? 'rtl' : 'ltr'} aria-label={stage === 'landing' ? text.sectionTitle : text.wizardTitle}>
      <header className="sticky top-0 z-10 grid grid-cols-[1fr_auto_1fr] items-center border-b border-border bg-background/95 px-4 py-3 backdrop-blur md:px-8">
        <button type="button" onClick={handleHeaderBack} className="inline-flex min-h-10 items-center gap-2 justify-self-start rounded-xl px-2 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
<ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />{headerBackLabel}
        </button>
        <span className="text-sm font-bold text-foreground">{stage === 'landing' ? text.sectionTitle : text.wizardTitle}</span>
        <button type="button" onClick={onBack} aria-label={text.close} className="flex size-10 items-center justify-center justify-self-end rounded-xl text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><X className="size-5" aria-hidden="true" /></button>
      </header>

      {stage === 'landing' ? (
        <div className="mx-auto grid min-h-[calc(100dvh-4rem)] max-w-7xl items-center gap-8 px-4 py-8 md:px-8 lg:grid-cols-[1.03fr_.97fr] lg:py-12">
          <section className="flex flex-col items-start gap-5 rounded-[2rem] border border-border bg-card p-6 shadow-sm sm:p-10 lg:p-12">
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-secondary px-3 py-1.5 text-xs font-bold uppercase tracking-[0.14em] text-primary-deep"><Sparkles className="size-4" aria-hidden="true" />{text.eyebrow}</span>
            <h1 className="max-w-2xl text-balance text-4xl font-bold leading-[1.08] tracking-tight text-foreground sm:text-5xl lg:text-6xl">{text.headline}</h1>
            <p className="max-w-xl text-pretty text-base leading-relaxed text-muted-foreground sm:text-lg">{text.intro}</p>
            <button type="button" onClick={() => setStage('material')} className="mt-2 inline-flex min-h-12 items-center gap-3 rounded-2xl bg-primary px-6 py-3 font-bold text-primary-foreground shadow-sm transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
              <Upload className="size-5" aria-hidden="true" />{text.create}<ArrowRight className="size-4 rtl:rotate-180" aria-hidden="true" />
            </button>
          </section>

          <section className="relative flex min-h-[360px] items-center justify-center overflow-hidden rounded-[2rem] border border-border bg-gradient-to-br from-accent via-card to-secondary/70 p-6 sm:min-h-[460px]" aria-label="Summary preview illustration">
            <div className="absolute -end-14 -top-20 size-64 rounded-full bg-primary/10 blur-3xl" />
            <div className="absolute -start-20 bottom-0 size-64 rounded-full bg-brand-cyan/15 blur-3xl" />
            <div className="relative w-full max-w-md rotate-[-3deg] rounded-3xl border border-border bg-background p-5 shadow-xl sm:p-7">
              <div className="flex items-center justify-between border-b border-border pb-4">
                <span className="flex items-center gap-2 text-sm font-bold"><span className="flex size-8 items-center justify-center rounded-xl bg-secondary text-primary"><BookOpenText className="size-4" aria-hidden="true" /></span>Field notes</span>
                <span className="rounded-full bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground">3 min read</span>
              </div>
              <div className="flex flex-col gap-3 py-5">
                <div className="h-3 w-4/5 rounded-full bg-foreground/80" />
                <div className="h-2 w-full rounded-full bg-muted-foreground/25" />
                <div className="h-2 w-11/12 rounded-full bg-muted-foreground/25" />
                <div className="my-2 rounded-2xl bg-accent/70 p-4">
                  <span className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-accent-foreground"><Focus className="size-4" aria-hidden="true" />Main idea</span>
                  <div className="h-2 w-5/6 rounded-full bg-accent-foreground/40" />
                  <div className="mt-2 h-2 w-2/3 rounded-full bg-accent-foreground/30" />
                </div>
                <div className="flex items-center gap-3 rounded-2xl border border-border p-3"><span className="flex size-9 items-center justify-center rounded-xl bg-secondary text-primary"><Check className="size-5" aria-hidden="true" /></span><span className="flex-1"><span className="block h-2 w-28 rounded-full bg-foreground/60" /><span className="mt-2 block h-2 w-20 rounded-full bg-muted-foreground/25" /></span><ChevronDown className="size-4 text-muted-foreground" aria-hidden="true" /></div>
              </div>
              <p className="text-sm italic text-muted-foreground">A pocket-sized view of the big picture.</p>
            </div>
            <div className="absolute bottom-7 end-4 flex max-w-[210px] rotate-[4deg] items-center gap-3 rounded-2xl border border-border bg-card p-3 shadow-lg sm:bottom-10 sm:end-8"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-secondary text-primary"><FileText className="size-5" aria-hidden="true" /></span><span className="text-xs font-semibold leading-relaxed text-foreground">{text.benefit}</span></div>
          </section>
        </div>
      ) : null}

      {stage === 'material' ? (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-8 md:px-8 md:py-12">
          <Stepper active={0} text={text} />
          <div className="flex flex-col gap-2 text-center"><h1 className="text-3xl font-bold tracking-tight">{text.source}</h1><p className="text-muted-foreground">{text.sourceIntro}</p></div>
          <div className="rounded-3xl border border-border bg-card p-4 shadow-sm sm:p-6">
            {!source ? (
              <ul className="grid gap-3 sm:grid-cols-2">
                {sources.map((item) => {
                  const Icon = SOURCE_ICONS[item.id]
                  const icon = <span className="flex size-12 items-center justify-center rounded-2xl bg-secondary text-primary">{Icon ? <Icon className="size-6" aria-hidden="true" /> : <svg viewBox="0 0 24 24" className="size-6 fill-current" aria-hidden="true"><path d={item.id === 'youtube' ? siYoutube.path : siWikipedia.path} /></svg>}</span>
                  return <li key={item.id}><button type="button" onClick={() => chooseSource(item.id)} className="group flex min-h-36 w-full flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-background/80 p-5 text-center transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{icon}<span className="font-bold group-hover:text-primary">{item.title}</span>{item.id === 'file' ? <span className="text-xs text-muted-foreground">{text.fileHint}</span> : null}</button></li>
                })}
              </ul>
            ) : (
              <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
                <div className="flex items-center justify-between gap-3"><h2 className="text-xl font-bold">{sources.find((item) => item.id === source)?.title}</h2><button type="button" onClick={() => setSource(null)} className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"><ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />{text.back}</button></div>
                {source === 'text' ? <label className="flex flex-col gap-2 text-sm font-semibold">{text.textLabel}<textarea rows={8} value={value} onChange={(event) => setValue(event.target.value)} className="w-full resize-y rounded-2xl border border-input bg-background px-4 py-3 text-base font-normal outline-none focus:border-primary focus:ring-2 focus:ring-primary/25" /></label> : source !== 'file' ? <label className="flex flex-col gap-2 text-sm font-semibold">{text.linkLabel}<input value={value} onChange={(event) => setValue(event.target.value)} placeholder={source === 'youtube' ? 'https://youtube.com/…' : 'https://…'} className="h-12 rounded-2xl border border-input bg-background px-4 text-base font-normal outline-none focus:border-primary focus:ring-2 focus:ring-primary/25" /></label> : <div onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files[0]) }} className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border bg-muted/30 p-5 text-center">
                  <FileUp className="size-7 text-primary" aria-hidden="true" /><span className="font-semibold">{file?.name ?? text.fileHint}</span><label className="cursor-pointer text-sm font-semibold text-primary underline underline-offset-4">{text.chooseFile}<input type="file" accept=".pdf,.doc,.docx,.txt,.md" className="sr-only" onChange={(event) => acceptFile(event.target.files?.[0])} /></label>
                </div>}
                <button type="button" disabled={!sourceIsReady} onClick={() => setStage('settings')} className="inline-flex min-h-12 items-center justify-center gap-2 self-end rounded-xl bg-primary px-5 font-bold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">{text.continue}<ArrowRight className="size-4 rtl:rotate-180" aria-hidden="true" /></button>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {stage === 'settings' ? (
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-4 py-8 md:px-8 md:py-10">
          <Stepper active={1} text={text} />
          <div className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-8">
            <div className="mb-6 flex items-center gap-3 rounded-2xl bg-muted/60 p-3"><span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-secondary text-primary"><FileText className="size-5" aria-hidden="true" /></span><span className="min-w-0 flex-1 truncate text-sm font-semibold">{selectedName}</span><button type="button" onClick={() => { setFile(null); setSource(null); setStage('material') }} aria-label={text.remove} className="flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-background hover:text-foreground"><X className="size-4" aria-hidden="true" /></button></div>
            <label className="mb-3 block text-lg font-bold">{text.pages}</label>
            <div className="flex flex-wrap gap-2" role="group" aria-label={text.pages}>{[2, 4, 6, 8, 10].map((count) => <button key={count} type="button" aria-pressed={pages === count} onClick={() => setPages(count)} className={`min-h-10 rounded-full border px-4 text-sm font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${pages === count ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-muted/60 text-foreground hover:border-primary/50'}`}>{count} {lang === 'ar' ? 'صفحات' : lang === 'fr' ? 'pages' : 'pages'}</button>)}</div>
            <label htmlFor="summary-focus" className="mt-7 flex flex-col gap-2 text-sm font-semibold">{text.focus}<span className="text-xs font-normal text-muted-foreground">{text.focusHint}</span><textarea id="summary-focus" value={focus} onChange={(event) => setFocus(event.target.value)} rows={3} className="w-full resize-y rounded-2xl border border-input bg-background px-4 py-3 text-base font-normal outline-none focus:border-primary focus:ring-2 focus:ring-primary/25" /></label>
            <div className="mt-3 flex flex-wrap gap-2">{text.focusIdeas.map((idea) => <button key={idea} type="button" onClick={() => setFocus((current) => current.includes(idea) ? current.replace(idea, '').trim() : [current, idea].filter(Boolean).join(', '))} className={`rounded-full border px-3 py-2 text-xs font-semibold transition ${focus.includes(idea) ? 'border-primary/40 bg-secondary text-primary-deep' : 'border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-primary'}`}><span className="me-1.5 text-primary">•</span>{idea}</button>)}</div>
            <label htmlFor="summary-language" className="mb-2 mt-7 block text-lg font-bold">{text.language}</label>
            <div className="relative"><Languages className="pointer-events-none absolute start-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><select id="summary-language" value={language} onChange={(event) => setLanguage(event.target.value as Lang)} className="h-14 w-full appearance-none rounded-2xl border border-input bg-background ps-12 pe-12 text-base font-semibold outline-none focus:border-primary focus:ring-2 focus:ring-primary/25"><option value="en">{text.english}</option><option value="fr">{text.french}</option><option value="ar">{text.arabic}</option></select><ChevronDown className="pointer-events-none absolute end-4 top-1/2 size-4 -translate-y-1/2" aria-hidden="true" /></div>
            <div className="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between"><button type="button" onClick={() => setStage('material')} className="min-h-11 rounded-xl border border-border px-5 font-semibold transition hover:bg-muted">{text.stepMaterial}</button><button type="button" onClick={() => { setProgress(0); setStage('loading') }} className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 font-bold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Sparkles className="size-4" aria-hidden="true" />{text.start}</button></div>
          </div>
        </div>
      ) : null}

      {stage === 'loading' || stage === 'complete' ? (
        <div className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-3xl flex-col items-center justify-center gap-6 px-4 py-8 text-center">
          <Stepper active={2} text={text} />
          <div className="w-full rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-10">
            <span className="mx-auto mb-5 flex size-16 items-center justify-center rounded-2xl bg-secondary text-primary">{stage === 'complete' ? <Check className="size-8" aria-hidden="true" /> : <LoaderCircle className="size-8 animate-spin motion-reduce:animate-none" aria-hidden="true" />}</span>
            <h1 className="text-2xl font-bold sm:text-3xl">{stage === 'complete' ? text.ready : text.working}</h1><p className="mx-auto mt-2 max-w-lg text-muted-foreground">{stage === 'complete' ? text.readyText : text.workingText}</p>
            <div className="mt-8 text-start"><div className="mb-2 flex items-center justify-between gap-3 text-sm"><span className="font-semibold">{text.stepSummary}</span><span className="tabular-nums text-muted-foreground">{progress}%</span></div><div className="h-3 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={text.stepSummary} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><div className="h-full rounded-full bg-gradient-to-r from-primary to-brand-cyan transition-[width] duration-200" style={{ width: `${progress}%` }} /></div></div>
            <div className="mt-6 flex items-center gap-3 rounded-2xl border border-border bg-background/70 p-4 text-start"><FileText className="size-5 shrink-0 text-primary" aria-hidden="true" /><span className="min-w-0 flex-1 truncate text-sm font-semibold">{selectedName}</span><span className="text-xs text-muted-foreground">{pages} {text.pageUnit}</span></div>
            {stage === 'complete' ? <button type="button" onClick={onBack} className="mt-7 min-h-11 rounded-xl bg-primary px-6 font-bold text-primary-foreground hover:bg-primary-deep">{text.back}</button> : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function Stepper({ active, text }: { active: number; text: (typeof COPY)['en'] }) {
  const labels = [text.stepMaterial, text.stepSettings, text.stepSummary]
  return <ol className="mx-auto flex w-full max-w-xl items-start" aria-label={text.progressLabel}>{labels.map((label, index) => <li key={label} className="relative flex flex-1 flex-col items-center gap-2 text-center text-xs font-semibold sm:text-sm"><span className={`relative z-[1] flex size-9 items-center justify-center rounded-full border-2 ${index <= active ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-muted-foreground'}`}>{index < active ? <Check className="size-4" aria-hidden="true" /> : index + 1}</span><span className={index <= active ? 'text-foreground' : 'text-muted-foreground'}>{label}</span>{index < labels.length - 1 ? <span className={`absolute start-[calc(50%+1.4rem)] top-4 h-0.5 w-[calc(100%-2.8rem)] ${index < active ? 'bg-primary' : 'bg-border'}`} aria-hidden="true" /> : null}</li>)}</ol>
}
