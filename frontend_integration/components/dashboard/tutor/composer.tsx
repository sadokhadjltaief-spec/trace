'use client'

import { useRef, useState } from 'react'
import { ArrowUp, BookOpen, FileText, LoaderCircle, Mic, Paperclip, RefreshCw, Square, X } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { cn } from '@/lib/utils'
import { SPEECH_LANG, type TutorCopy } from './tutor-copy'

type Recognition = {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start: () => void
  stop: () => void
}

function getRecognitionCtor(): (new () => Recognition) | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as Record<string, (new () => Recognition) | undefined>
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export type Attachment = {
  name: string
  size: number
  progress: number // 0-100 upload progress
  status: 'uploading' | 'ready' | 'error'
  error?: string
  docId?: string
  pages?: number
  readable?: number
  unreadable?: number[]
}

type Props = {
  copy: TutorCopy
  lang: Lang
  busy: boolean
  onSend: (text: string) => void
  onStop: () => void
  attachment?: Attachment | null
  onAttach?: (file: File) => void
  onRemoveAttachment?: () => void
  onTextbook?: () => void
}

const A = {
  fr: { attach: 'Joindre un PDF', remove: 'Retirer le PDF', replace: 'Remplacer', pages: 'pages lues', of: 'sur', ocr: 'pages scannées (OCR nécessaire)', book: 'Transformer en manuel 3D', uploading: 'Envoi…', placeholder: 'Pose une question sur ton PDF…' },
  en: { attach: 'Attach a PDF', remove: 'Remove the PDF', replace: 'Replace', pages: 'pages read', of: 'of', ocr: 'scanned pages (OCR needed)', book: 'Transform into 3D textbook', uploading: 'Uploading…', placeholder: 'Ask a question about your PDF…' },
  ar: { attach: 'أرفق ملف PDF', remove: 'إزالة الملف', replace: 'استبدال', pages: 'صفحات مقروءة', of: 'من', ocr: 'صفحات ممسوحة (تحتاج OCR)', book: 'حوّله إلى كتاب ثلاثي الأبعاد', uploading: 'جارٍ الإرسال…', placeholder: 'اسأل عن ملفك…' },
}
const mb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} Mo` : `${Math.max(1, Math.round(n / 1024))} Ko`)

export function Composer({ copy, lang, busy, onSend, onStop, attachment, onAttach, onRemoveAttachment, onTextbook }: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const L = A[lang]
  const [input, setInput] = useState('')
  const [listening, setListening] = useState(false)
  const [canDictate] = useState(() => getRecognitionCtor() !== null)
  const recognition = useRef<Recognition | null>(null)

  const submit = () => {
    const text = input.trim()
    if (!text || busy) return
    recognition.current?.stop()
    onSend(text)
    setInput('')
  }

  const toggleDictation = () => {
    if (listening) {
      recognition.current?.stop()
      return
    }
    const Ctor = getRecognitionCtor()
    if (!Ctor) return
    const base = input ? `${input.trimEnd()} ` : ''
    const rec = new Ctor()
    rec.lang = SPEECH_LANG[lang]
    rec.interimResults = true
    rec.continuous = true
    rec.onresult = (event) => {
      const transcript = Array.from(event.results, (r) => r[0].transcript).join('')
      setInput(base + transcript)
    }
    rec.onend = () => setListening(false)
    rec.onerror = () => setListening(false)
    recognition.current = rec
    rec.start()
    setListening(true)
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      className="flex flex-col gap-2 rounded-3xl border border-border bg-card p-3 shadow-lg shadow-ink/5 transition focus-within:border-primary/60 focus-within:ring-4 focus-within:ring-primary/10"
    >
      <label htmlFor="tutor-input" className="sr-only">
        {copy.placeholder}
      </label>
      {attachment ? (
        <div className={cn('flex flex-wrap items-center gap-3 rounded-2xl border px-3 py-2', attachment.status === 'error' ? 'border-destructive/40 bg-destructive/10' : 'border-border bg-muted/50')}>
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive"><FileText className="size-5" aria-hidden="true" /></span>
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-semibold text-foreground" dir="ltr">{attachment.name}</span>
            <span className="text-xs text-muted-foreground">
              {mb(attachment.size)}
              {attachment.status === 'uploading' ? ` · ${L.uploading} ${attachment.progress} %` : null}
              {attachment.status === 'ready' ? ` · ${attachment.readable} ${L.of} ${attachment.pages} ${L.pages}` : null}
              {attachment.status === 'ready' && attachment.unreadable?.length ? ` · ${attachment.unreadable.length} ${L.ocr}` : null}
            </span>
            {attachment.status === 'uploading' ? (
              <span className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-border"><span className="block h-full rounded-full bg-primary transition-[width]" style={{ width: `${attachment.progress}%` }} /></span>
            ) : null}
            {attachment.status === 'error' ? <span role="alert" className="text-xs font-semibold text-destructive">{attachment.error}</span> : null}
          </span>
          {attachment.status === 'uploading' ? <LoaderCircle className="size-4 animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" /> : null}
          {attachment.status === 'ready' && onTextbook && attachment.readable ? (
            <button type="button" onClick={onTextbook} className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground transition hover:bg-primary-deep">
              <BookOpen className="size-3.5" aria-hidden="true" />{L.book}
            </button>
          ) : null}
          <button type="button" onClick={() => fileRef.current?.click()} title={L.replace} aria-label={L.replace} className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"><RefreshCw className="size-4" aria-hidden="true" /></button>
          <button type="button" onClick={onRemoveAttachment} title={L.remove} aria-label={L.remove} className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"><X className="size-4" aria-hidden="true" /></button>
        </div>
      ) : null}
      <input ref={fileRef} type="file" accept="application/pdf,.pdf" className="sr-only" tabIndex={-1} aria-hidden="true"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onAttach?.(f); e.target.value = '' }} />
      <textarea
        id="tutor-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== 'Enter' || e.shiftKey) return
          if (e.nativeEvent.isComposing || e.keyCode === 229) return
          e.preventDefault()
          submit()
        }}
        rows={1}
        placeholder={attachment?.status === 'ready' ? L.placeholder : copy.placeholder}
        className="field-sizing-content max-h-48 min-h-12 w-full resize-none bg-transparent px-2 py-1.5 text-base text-foreground placeholder:text-muted-foreground focus:outline-none"
      />
      <div className="flex items-center justify-end gap-2">
        {onAttach ? (
          <button type="button" onClick={() => fileRef.current?.click()} aria-label={L.attach} title={L.attach}
            className="me-auto inline-flex h-10 items-center gap-1.5 rounded-full bg-muted px-3 text-sm font-semibold text-muted-foreground transition hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50">
            <Paperclip className="size-4" aria-hidden="true" /><span>PDF</span>
          </button>
        ) : null}
        {canDictate && (
          <button
            type="button"
            onClick={toggleDictation}
            aria-label={listening ? copy.micStop : copy.micStart}
            aria-pressed={listening}
            title={listening ? copy.micStop : copy.micStart}
            className={cn(
              'flex size-10 items-center justify-center rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
              listening ? 'animate-pulse bg-destructive text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-primary',
            )}
          >
            <Mic className="size-5" aria-hidden="true" />
          </button>
        )}
        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label={copy.stop}
            title={copy.stop}
            className="flex size-10 items-center justify-center rounded-full bg-foreground text-background transition hover:opacity-90"
          >
            <Square className="size-4 fill-current" aria-hidden="true" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            aria-label={copy.send}
            title={copy.send}
            className="flex size-10 items-center justify-center rounded-full bg-primary text-primary-foreground transition hover:bg-primary-deep disabled:bg-muted disabled:text-muted-foreground"
          >
            <ArrowUp className="size-5" aria-hidden="true" />
          </button>
        )}
      </div>
    </form>
  )
}
