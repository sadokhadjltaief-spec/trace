'use client'

import { useEffect, useRef } from 'react'
import type { UIMessage } from 'ai'
import { WaslaLogo } from '@/components/wasla-logo'
import type { Lang } from '@/lib/translations'
import { Composer } from './composer'
import { Markdown } from './markdown'
import { messageText } from './use-conversations'
import type { TutorCopy } from './tutor-copy'
import { useTraceChat } from './use-trace-chat'

export type TutorContext = {
  name: string
  level: string
  explanations: string
  information: string
  environment: string
  timing: string
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
  const { messages, sendMessage, status, stop, error, regenerate, quickReplies } = useTraceChat({
    id: chatId,
    messages: initialMessages,
    lang,
    student: { name: context.name || firstName, level: context.level },
    startText: copy.start,
  })

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
  const composer = <Composer copy={copy} lang={lang} busy={busy} onSend={send} onStop={stop} />

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-8 overflow-y-auto px-4 py-10">
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
      <div className="flex-1 overflow-y-auto px-4 py-6" aria-live="polite">
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
                  <Markdown>{text}</Markdown>
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
          {composer}
          <p className="text-center text-xs text-muted-foreground">{copy.disclaimer}</p>
        </div>
      </div>
    </>
  )
}
