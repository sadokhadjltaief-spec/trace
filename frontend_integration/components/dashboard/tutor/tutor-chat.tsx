'use client'

import { useEffect, useRef, useState } from 'react'
import type { UIMessage } from 'ai'
import { WaslaLogo } from '@/components/wasla-logo'
import type { Lang } from '@/lib/translations'
import { Composer, type Attachment } from './composer'
import { LessonView } from '../lesson/lesson-view'
import { authHeader } from '@/lib/auth'
import { Markdown } from './markdown'
import { messageText } from './use-conversations'
import type { TutorCopy } from './tutor-copy'
import { useTraceChat } from './use-trace-chat'
import { BookOpen, Clapperboard, FileUp, ImageIcon } from 'lucide-react'

const MEDIA_COPY = {
  fr: { image: 'Générer une image', video: 'Générer une vidéo', hint: 'sur ta dernière question', book: 'Ouvrir en manuel 3D', drop: 'Dépose ton PDF ici', dropHint: 'PDF · 25 Mo maximum', notPdf: 'Seuls les fichiers PDF sont acceptés.', tooBig: 'Le PDF dépasse 25 Mo.', failed: 'L’envoi a échoué. Vérifie que le serveur WASLA est lancé.' },
  en: { image: 'Generate an image', video: 'Generate a video', hint: 'about your last question', book: 'Open as 3D textbook', drop: 'Drop your PDF here', dropHint: 'PDF · up to 25 MB', notPdf: 'Only PDF files are accepted.', tooBig: 'The PDF is larger than 25 MB.', failed: 'The upload failed. Check that the WASLA server is running.' },
  ar: { image: 'أنشئ صورة', video: 'أنشئ فيديو', hint: 'حول سؤالك الأخير', book: 'افتح ككتاب ثلاثي الأبعاد', drop: 'أفلت ملف PDF هنا', dropHint: 'PDF · حتى 25 ميغابايت', notPdf: 'تُقبل ملفات PDF فقط.', tooBig: 'حجم الملف أكبر من 25 ميغابايت.', failed: 'فشل الإرسال. تأكد من تشغيل خادم وصلة.' },
}
// one attached PDF per conversation (kept while the page is open)
const ATTACHED = new Map<string, Attachment>()

// the reply is shown only after the engine's checks passed; it then appears progressively (not in calm mode)
function attachmentDoc(chatId: string) {
  const a = ATTACHED.get(chatId)
  return a?.status === 'ready' ? a.docId ?? null : null
}

function Reveal({ text }: { text: string }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    setN(0)
    const step = Math.max(4, Math.ceil(text.length / 60))
    const t = window.setInterval(() => setN((x: number) => { if (x + step >= text.length) { window.clearInterval(t); return text.length } return x + step }), 16)
    return () => window.clearInterval(t)
  }, [text])
  return <Markdown>{n >= text.length ? text : text.slice(0, n)}</Markdown>
}

export type TutorContext = {
  name: string
  level: string
  explanations: string
  information: string
  environment: string
  timing: string
  prefs?: Record<string, string | null>
  onProgress?: (understood: number) => void
}

type Props = {
  chatId: string
  initialMessages: UIMessage[]
  copy: TutorCopy
  lang: Lang
  firstName: string
  context: TutorContext
  onMessages: (id: string, messages: UIMessage[]) => void
}

export function TutorChat({ chatId, initialMessages, copy, lang, firstName, context, onMessages }: Props) {
  // TRACE engine session (diagnosis -> hints -> find the mistake -> new question) instead of a free LLM chat
  const { messages, sendMessage, status, stop, error, regenerate, quickReplies, requestMedia } = useTraceChat({
    id: chatId,
    messages: initialMessages,
    lang,
    student: { name: context.name || firstName, level: context.level },
    startText: copy.start,
    preferences: context.prefs,
    onProgress: context.onProgress,
    docId: attachmentDoc(chatId),
  })
  const [attachment, setAttachmentState] = useState<Attachment | null>(() => ATTACHED.get(chatId) ?? null)
  const setAttachment = (a: Attachment | null) => { if (a) ATTACHED.set(chatId, a); else ATTACHED.delete(chatId); setAttachmentState(a) }
  const [dragging, setDragging] = useState(false)
  const [book, setBook] = useState<{ docId?: string; text?: string; name?: string } | null>(null)

  function upload(file: File) {
    const MC = MEDIA_COPY[lang]
    const base = { name: file.name, size: file.size, progress: 0 }
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') { setAttachment({ ...base, status: 'error', error: MC.notPdf }); return }
    if (file.size > 25 * 1024 * 1024) { setAttachment({ ...base, status: 'error', error: MC.tooBig }); return }
    setAttachment({ ...base, status: 'uploading' })
    const form = new FormData()
    form.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/tutor/documents')
    Object.entries(authHeader()).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) setAttachment({ ...base, status: 'uploading', progress: Math.min(99, Math.round((e.loaded / e.total) * 100)) }) }
    xhr.onerror = () => setAttachment({ ...base, status: 'error', error: MC.failed })
    xhr.onload = () => {
      let data: { doc_id?: string; pages?: number; readable_pages?: number; unreadable_pages?: number[]; needs_ocr?: boolean; detail?: { code?: string } & Record<string, string> } = {}
      try { data = JSON.parse(xhr.responseText) } catch { /* not JSON */ }
      if (xhr.status >= 400 || !data.doc_id) {
        const d = data.detail
        setAttachment({ ...base, status: 'error', error: (d && (d[lang] || d.fr)) || MC.failed })
        return
      }
      if (data.needs_ocr) {
        setAttachment({ ...base, status: 'error', progress: 100, error: { fr: 'Ce PDF est scanné : aucune page n’a de texte lisible. Il faut une reconnaissance de texte (OCR), non installée.', en: 'This PDF is scanned: no page has readable text. It needs OCR, which is not installed.', ar: 'هذا الملف ممسوح ضوئيًا ولا يحتوي على نص مقروء. يحتاج إلى OCR غير المثبّت.' }[lang] })
        return
      }
      setAttachment({ ...base, status: 'ready', progress: 100, docId: data.doc_id, pages: data.pages, readable: data.readable_pages, unreadable: data.unreadable_pages })
    }
    xhr.send(form)
  }
  const calm = context.prefs?.learningEnvironment === 'calm'
  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')?.id
  const M = MEDIA_COPY[lang]

  const initial = useRef(initialMessages)
  useEffect(() => {
    if (messages.length > 0 && messages !== initial.current) onMessages(chatId, messages)
  }, [chatId, messages, onMessages])

  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, status])

  const busy = status === 'submitted' || status === 'streaming'
  const send = (text: string) => sendMessage({ text })
  const composer = (
    <Composer copy={copy} lang={lang} busy={busy} onSend={send} onStop={stop} attachment={attachment}
      onAttach={upload} onRemoveAttachment={() => setAttachment(null)}
      onTextbook={attachment?.docId ? () => setBook({ docId: attachment.docId, name: attachment.name }) : undefined} />
  )
  const dropProps = {
    onDragOver: (e: React.DragEvent) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); setDragging(true) } },
    onDragLeave: (e: React.DragEvent) => { if (e.currentTarget === e.target) setDragging(false) },
    onDrop: (e: React.DragEvent) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) upload(f) },
  }
  const dropOverlay = dragging ? (
    <div className="pointer-events-none absolute inset-3 z-30 flex flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-primary bg-primary/10 backdrop-blur-sm">
      <FileUp className="size-10 text-primary" aria-hidden="true" />
      <p className="text-lg font-bold text-foreground">{M.drop}</p>
      <p className="text-sm text-muted-foreground">{M.dropHint}</p>
    </div>
  ) : null

  if (book) return <LessonView lang={lang} source={book} onExit={() => setBook(null)} />

  if (messages.length === 0) {
    return (
      <div {...dropProps} className="relative flex flex-1 flex-col items-center justify-center gap-8 overflow-y-auto px-4 py-10">
        {dropOverlay}
        <div className="flex flex-col items-center gap-3 text-center">
          <WaslaLogo className="h-20 w-40" />
          <h1 className="text-balance text-2xl font-bold text-foreground md:text-3xl">{copy.greeting(firstName)}</h1>
          <p className="text-pretty text-muted-foreground">{copy.subtitle}</p>
        </div>
        <div className="flex w-full max-w-2xl flex-col items-center gap-4">
          <div className="w-full">{composer}</div>
          <button type="button" onClick={() => send(copy.start)} className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm text-foreground transition hover:border-primary/60 hover:text-primary">
            {copy.start}
          </button>
        </div>
      </div>
    )
  }

  return (
    <>
      <div {...dropProps} className="relative flex-1 overflow-y-auto px-4 py-6" aria-live="polite">
        {dropOverlay}
        <ol className="mx-auto flex w-full max-w-3xl flex-col gap-6">
          {messages.map((message) => {
            const text = messageText(message)
            if (message.role === 'user') {
              return (
                <li key={message.id} className="flex justify-end">
                  <p className="sr-only">{copy.you}:</p>
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl rounded-ee-md bg-secondary px-4 py-3 text-secondary-foreground">
                    {text}
                  </div>
                </li>
              )
            }
            return (
              <li key={message.id} className="flex gap-3">
                <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                  W
                </span>
                <div className="min-w-0 flex-1 text-foreground/90">
                  <p className="sr-only">{copy.tutor}:</p>
                  {message.id === lastAssistant && !calm ? <Reveal text={text} /> : <Markdown>{text}</Markdown>}
                  {text.length > 220 && status !== 'submitted' ? (
                    <button type="button" onClick={() => setBook({ text })} className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs font-semibold text-muted-foreground transition hover:border-primary/60 hover:text-primary">
                      <BookOpen className="size-3.5" aria-hidden="true" />{M.book}
                    </button>
                  ) : null}
                </div>
              </li>
            )
          })}

          {status === 'submitted' && (
            <li className="flex items-center gap-3">
              <span className="flex size-8 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                W
              </span>
              <span className="flex gap-1" aria-label={copy.thinking} role="status">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="size-2 animate-bounce rounded-full bg-primary/70"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </span>
            </li>
          )}

          {status !== 'submitted' && quickReplies.length > 0 && (
            <li>
              <ul className="flex flex-wrap justify-center gap-2">
                {quickReplies.map((s) => (
                  <li key={s}>
                    <button type="button" onClick={() => send(s)} className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm text-foreground transition hover:border-primary/60 hover:text-primary">
                      {s}
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          )}

          {error && (
            <li className="flex flex-wrap items-center gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {copy.error}
              <button type="button" onClick={() => regenerate()} className="font-semibold underline underline-offset-4">
                {copy.retry}
              </button>
            </li>
          )}
        </ol>
        <div ref={endRef} />
      </div>

      <div className="px-4 pb-4">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" disabled={busy} onClick={() => requestMedia('image')} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground transition hover:border-primary/60 hover:text-primary disabled:opacity-50">
              <ImageIcon className="size-3.5" aria-hidden="true" />{M.image}
            </button>
            <button type="button" disabled={busy} onClick={() => requestMedia('video')} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground transition hover:border-primary/60 hover:text-primary disabled:opacity-50">
              <Clapperboard className="size-3.5" aria-hidden="true" />{M.video}
            </button>
            <span className="text-xs text-muted-foreground">{M.hint}</span>
          </div>
          {composer}
          <p className="text-center text-xs text-muted-foreground">{copy.disclaimer}</p>
        </div>
      </div>
    </>
  )
}
