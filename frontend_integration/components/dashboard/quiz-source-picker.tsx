'use client'

import { useState } from 'react'
import { ArrowLeft, ClipboardPaste, FileUp, type LucideIcon } from 'lucide-react'
import { siWikipedia, siYoutube } from 'simple-icons'
import type { DashboardCopy } from './dashboard-copy'
import type { Lang } from '@/lib/translations'
import { PreparationExperience } from './preparation-experience'

type SourceId = 'file' | 'text' | 'youtube' | 'wikipedia'
type Source = { id: SourceId; title: string; description: string; icon?: LucideIcon; tone: string }

export function QuizSourcePicker({ copy, onBack, kind = 'quiz', lang }: { copy: DashboardCopy; onBack: () => void; kind?: 'quiz' | 'flashcards'; lang: Lang }) {
  const [source, setSource] = useState<SourceId | null>(null)
  const [fileName, setFileName] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [value, setValue] = useState('')
  const [details, setDetails] = useState('')
  const [preparing, setPreparing] = useState(false)

  const sources: Source[] = [
    { id: 'file', title: copy.quiz.uploadFile, description: copy.quiz.fileDescription, icon: FileUp, tone: 'bg-accent text-accent-foreground' },
    { id: 'text', title: copy.quiz.pasteText, description: copy.quiz.textDescription, icon: ClipboardPaste, tone: 'bg-secondary text-primary-deep' },
    { id: 'youtube', title: copy.quiz.youtube, description: copy.quiz.youtubeDescription, tone: 'bg-destructive/10 text-destructive' },
    { id: 'wikipedia', title: copy.quiz.wikipedia, description: copy.quiz.wikipediaDescription, tone: 'bg-accent text-accent-foreground' },
  ]

  const selectedSource = sources.find((item) => item.id === source)
  const isReady = source === 'file' ? fileName.length > 0 : Boolean(value.trim())
  const flashcardCopy = {
    en: { intro: 'Choose a source to turn into a stack of study cards.', progress: 'Flashcard setup, step 1 of 3' },
    fr: { intro: 'Choisis une source pour créer tes cartes mémo.', progress: 'Création des cartes, étape 1 sur 3' },
    ar: { intro: 'اختر مصدرًا لتحويله إلى بطاقات مراجعة.', progress: 'إعداد البطاقات، الخطوة ١ من ٣' },
  }[lang]

  if (preparing) {
    return <PreparationExperience copy={copy} kind={kind} lang={lang} fileNames={[fileName || selectedSource?.title || copy.quiz.title]} details={details} onBack={onBack} files={source === 'file' ? files : []} text={source === 'file' ? '' : value} source={source ?? 'file'} />
  }

  function chooseSource(id: SourceId) {
    setSource(id)
    setFileName('')
    setValue('')
    setDetails('')
    setPreparing(false)
  }

  return (
    <section className="min-h-[calc(100dvh-5rem)] bg-muted/40">
      <header className="grid grid-cols-[1fr_auto_1fr] items-center border-b border-border bg-card px-4 py-3 md:px-8">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-2 justify-self-start rounded-lg px-2 py-1.5 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
          <span>{copy.nav.home}</span>
        </button>
        <h1 className="text-lg font-bold text-foreground">{kind === 'flashcards' ? copy.tools.flashcards.title : copy.quiz.title}</h1>
        <span aria-hidden="true" />
      </header>

      <div className="mx-auto flex w-full max-w-5xl flex-col items-center gap-8 px-4 py-8 md:px-8 md:py-10">
        <div className="flex w-40 items-center gap-2" role="group" aria-label={kind === 'flashcards' ? flashcardCopy.progress : copy.quiz.setupProgress}>
          {[0, 1, 2].map((step) => (
            <span key={step} className={`h-1.5 flex-1 rounded-full ${step === 0 ? 'bg-primary' : 'bg-primary/25'}`} />
          ))}
        </div>

        <div className="flex flex-col items-center gap-3 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground">{kind === 'flashcards' ? ({ en: 'Build your flashcards', fr: 'Créer tes cartes mémo', ar: 'أنشئ بطاقات المراجعة' } as const)[lang] : copy.quiz.chooseSource}</h2>
          <p className="max-w-xl text-pretty text-base text-muted-foreground md:text-lg">{kind === 'flashcards' ? flashcardCopy.intro : copy.quiz.chooseSourceDescription}</p>
        </div>

        <div className="w-full rounded-2xl border border-border bg-card p-4 sm:p-6">
          {!source ? (
            <ul className="grid gap-3 sm:grid-cols-2">
              {sources.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => chooseSource(item.id)} className="group flex min-h-40 w-full flex-col items-center justify-center gap-4 rounded-2xl border border-border bg-background/70 p-5 text-center transition hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <span className={`flex size-14 items-center justify-center rounded-full ${item.tone}`}>
                      {item.icon ? (
                        <item.icon className="size-6" aria-hidden="true" />
                      ) : (
                        <svg viewBox="0 0 24 24" className="size-6 fill-current" aria-hidden="true">
                          <path d={item.id === 'youtube' ? siYoutube.path : siWikipedia.path} />
                        </svg>
                      )}
                    </span>
                    <span className="flex flex-col gap-1">
                      <span className="font-bold text-foreground group-hover:text-primary">{item.title}</span>
                      <span className="text-sm text-muted-foreground">{item.description}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : selectedSource ? (
            <form
              onSubmit={(event) => {
                event.preventDefault()
                if (isReady) setPreparing(true)
              }}
              className="mx-auto flex w-full max-w-2xl flex-col gap-5"
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-xl font-bold text-foreground">{selectedSource.title}</h3>
                <button type="button" onClick={() => { setSource(null); setFileName(''); setValue(''); setDetails('') }} className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
                  {copy.quiz.back}
                </button>
              </div>

              {source === 'file' ? (
                <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-border bg-muted/40 p-6 text-center transition hover:border-primary/50">
                  <FileUp className="size-8 text-primary" aria-hidden="true" />
                  <span className="font-semibold text-foreground">{copy.quiz.fileLabel}</span>
                  <span className="text-sm text-muted-foreground">{fileName || copy.quiz.fileHint}</span>
                  <input type="file" multiple accept=".pdf,.doc,.docx,.txt,.md" className="sr-only" onChange={(event) => {
                    setFiles(Array.from(event.target.files ?? []))
                    setFileName(Array.from(event.target.files ?? [], (file) => file.name).join(', '))
                  }} />
                </label>
              ) : source === 'text' ? (
                <label className="flex flex-col gap-2 text-sm font-semibold text-foreground">
                  {copy.quiz.textLabel}
                  <textarea required rows={8} value={value} onChange={(event) => { setValue(event.target.value) }} className="w-full resize-y rounded-xl border border-input bg-background px-4 py-3 text-base font-normal text-foreground outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/25" />
                </label>
              ) : (
                <label className="flex flex-col gap-2 text-sm font-semibold text-foreground">
                  {source === 'youtube' ? copy.quiz.youtubeLabel : copy.quiz.wikipediaLabel}
                  <input
                    required
                    type={source === 'youtube' ? 'url' : 'text'}
                    value={value}
                    onChange={(event) => { setValue(event.target.value) }}
                    placeholder={source === 'youtube' ? 'https://www.youtube.com/watch?v=…' : 'https://…'}
                    className="h-12 w-full rounded-xl border border-input bg-background px-4 text-base font-normal text-foreground outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/25"
                  />
                </label>
              )}

              {source !== 'file' || fileName ? (
                <label htmlFor="quiz-details" className="flex flex-col gap-2 text-sm font-semibold text-foreground">
                  {copy.preparation.optionalDetails}
                  <span className="text-xs font-normal text-muted-foreground">{copy.preparation.optional}</span>
                  <textarea id="quiz-details" value={details} onChange={(event) => setDetails(event.target.value)} rows={4} placeholder={copy.preparation.quizHint} className="w-full resize-y rounded-xl border border-input bg-background px-4 py-3 text-base font-normal text-foreground outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/25" />
                </label>
              ) : null}
              <button type="submit" disabled={!isReady} className="inline-flex min-h-12 items-center justify-center gap-2 self-start rounded-xl bg-primary px-5 py-3 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
                {kind === 'flashcards' ? ({ en: 'Create flashcards', fr: 'Créer des cartes mémo', ar: 'أنشئ بطاقات مراجعة' } as const)[lang] : copy.preparation.confirmQuiz}
              </button>
            </form>
          ) : null}
        </div>
      </div>
    </section>
  )
}
