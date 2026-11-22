'use client'

import { useState } from 'react'
import { ArrowLeft, FileUp, X } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import type { DashboardCopy } from './dashboard-copy'
import { PreparationExperience } from './preparation-experience'

export function StudyPlanFlow({ copy, onBack, lang }: { copy: DashboardCopy; onBack: () => void; lang: Lang }) {
  const [files, setFiles] = useState<File[]>([])
  const [details, setDetails] = useState('')
  const [dragging, setDragging] = useState(false)
  const [preparing, setPreparing] = useState(false)
  const text = copy.preparation

  if (preparing) {
    return <PreparationExperience copy={copy} kind="plan" lang={lang} fileNames={files.map((file) => file.name)} details={details} onBack={onBack} files={files} />
  }

  function addFiles(nextFiles: FileList | null) {
    if (!nextFiles) return
    setFiles(Array.from(nextFiles))
  }

  return (
    <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12" aria-labelledby="plan-title">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <button type="button" onClick={onBack} className="inline-flex min-h-10 items-center gap-2 self-start rounded-lg px-2 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
          {text.back}
        </button>

        <div className="rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-9">
          <div className="mb-7 flex flex-col gap-2">
            <span className="mb-1 flex size-12 items-center justify-center rounded-2xl bg-secondary text-primary"><FileUp className="size-6" aria-hidden="true" /></span>
            <h1 id="plan-title" className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">{copy.tools.plan.title}</h1>
            <p className="max-w-xl text-pretty text-muted-foreground">{text.planIntro}</p>
          </div>

          <label
            onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(event.dataTransfer.files) }}
            className={`flex min-h-48 cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-6 text-center transition focus-within:ring-2 focus-within:ring-ring ${dragging ? 'border-primary bg-secondary/50' : 'border-border bg-muted/30 hover:border-primary/50'}`}
          >
            <span className="flex size-12 items-center justify-center rounded-xl bg-accent text-accent-foreground"><FileUp className="size-6" aria-hidden="true" /></span>
            <span className="font-semibold text-foreground">{text.dropFiles}</span>
            <span className="text-sm text-muted-foreground">{text.orBrowse} · {text.supportedFiles}</span>
            <input type="file" multiple accept=".pdf,.doc,.docx,.txt,.md" className="sr-only" onChange={(event) => addFiles(event.target.files)} aria-label={text.dropFiles} />
          </label>

          {files.length > 0 ? (
            <ul className="mt-4 flex flex-col gap-2" aria-label={text.selectedFiles}>
              {files.map((file, index) => (
                <li key={`${file.name}-${index}`} className="flex min-w-0 items-center gap-3 rounded-xl border border-border bg-background px-3 py-2.5">
                  <FileUp className="size-4 shrink-0 text-primary" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{file.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{(file.size / (1024 * 1024)).toFixed(1)} MB</span>
                  <button type="button" onClick={() => setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index))} aria-label={`${text.removeFile} ${file.name}`} className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <X className="size-4" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          <label htmlFor="plan-details" className="mt-6 flex flex-col gap-2 text-sm font-semibold text-foreground">
            {text.optionalDetails}
            <span className="text-xs font-normal text-muted-foreground">{text.optional}</span>
            <textarea id="plan-details" value={details} onChange={(event) => setDetails(event.target.value)} rows={4} placeholder={text.planHint} className="w-full resize-y rounded-xl border border-input bg-background px-4 py-3 text-base font-normal text-foreground outline-none placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/25" />
          </label>

          <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button type="button" onClick={onBack} className="min-h-11 rounded-xl border border-border px-5 py-2.5 font-semibold text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{text.cancel}</button>
            <button type="button" disabled={files.length === 0} onClick={() => setPreparing(true)} className="min-h-11 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">{text.confirmPlan}</button>
          </div>
        </div>
      </div>
    </section>
  )
}
