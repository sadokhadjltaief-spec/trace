'use client'

// Replaces `useChat` (ai-sdk) with a TRACE session: start_session -> submit_answer (diagnosis) -> tutor_reply
// (hints, find-the-mistake, new question). Same return shape as useChat, so the chat UI is unchanged.
// Rules (C:\TRACE\docs\INTERFACE.md): no LLM call here, no diagnosis maths here, engine text is shown only if
// `shown_allowed` is true.

import { useCallback, useRef, useState } from 'react'
import type { UIMessage } from 'ai'
import type { Lang } from '@/lib/translations'

type SafeText = { text: string; lang: string; shown_allowed: boolean }
type QuestionView = { id: string; text: string; options: Record<string, string>; requires_confidence: boolean }
type Turn = {
  state: string
  message: SafeText
  expects: 'answer' | 'retry' | 'error_step' | 'explanation' | 'transfer_answer' | 'none'
  agenda: { step: number; total: number; next: string }
  question: QuestionView | null
  reconstruction: { id: string; problem: string; steps: string[] } | null
  grading: { correct: boolean | null; method: string; label: string }
}
type SessionState = { session_id: string; current_question: QuestionView | null; warnings: string[] }
type ChatAnswer = {
  on_topic: boolean
  method: 'computed' | 'rag_llm' | 'rag_extractive' | 'tutor_llm' | 'not_found' | 'refusal'
  label?: string
  answer: SafeText
  citations: { file: string; page: number; source_url: string | null }[]
}
type Summary = { outcome: SafeText; next_step: SafeText; diagnosis_names: Record<string, string>; status: string }

type Pending = { expects: Turn['expects']; question: QuestionView | null; steps: number }
type Stored = { sessionId: string | null; pending: Pending | null }

// one TRACE session per conversation (kept while the page is open)
const SESSIONS = new Map<string, Stored>()

// demo mode = the engine replays recorded LLM answers from its cache (works offline). On by default.
const DEMO = process.env.NEXT_PUBLIC_TRACE_DEMO !== 'false'
// "clear" = clear and structured mode preset (needs its own recording for the offline demo)
const PROFILE = process.env.NEXT_PUBLIC_TRACE_PROFILE === 'clear' ? { preset: 'clear_structured' } : {}

const T = {
  fr: {
    intro: 'Diagnostic : réponds avec la lettre, puis **sûr** ou **pas sûr**, et si tu veux pourquoi. Exemple : « A sûr, parce que… »',
    sure: 'sûr', unsure: 'pas sûr', step: 'Étape', of: 'sur', next: 'ensuite',
    needOption: 'Écris la lettre de ta réponse (A, B, C ou D), puis « sûr » ou « pas sûr ».',
    needLetter: 'Écris la lettre de ta réponse (A, B, C ou D).',
    needStep: 'Écris le numéro de l’étape fausse, puis pourquoi. Exemple : « 2 parce que… »',
    withheld: '_(Message retenu : les vérifications de sécurité n’ont pas été validées.)_',
    correct: 'Juste', wrong: 'Pas juste', newSession: 'Nouvelle séance', outcome: 'Résultat', nextStep: 'Prochaine étape',
    found: 'Erreur type trouvée',
    sources: 'Sources',
  },
  ar: {
    intro: 'التشخيص: أجب بالحرف، ثم **متأكّد** أو **غير متأكّد**، وإن شئت لماذا. مثال: «A متأكّد لأن…»',
    sure: 'متأكّد', unsure: 'غير متأكّد', step: 'الخطوة', of: 'من', next: 'بعد ذلك',
    needOption: 'اكتب حرف إجابتك (A أو B أو C أو D)، ثم «متأكّد» أو «غير متأكّد».',
    needLetter: 'اكتب حرف إجابتك (A أو B أو C أو D).',
    needStep: 'اكتب رقم الخطوة الخاطئة، ثم السبب. مثال: «2 لأن…»',
    withheld: '_(رسالة محجوبة: لم تنجح فحوص الأمان.)_',
    correct: 'صحيح', wrong: 'غير صحيح', newSession: 'حصة جديدة', outcome: 'النتيجة', nextStep: 'الخطوة التالية',
    found: 'الخطأ النمطي المكتشف',
    sources: 'المصادر',
  },
  en: {
    intro: 'Diagnosis: answer with the letter, then **sure** or **not sure**, and why if you like. Example: "A sure, because…"',
    sure: 'sure', unsure: 'not sure', step: 'Step', of: 'of', next: 'next',
    needOption: 'Type the letter of your answer (A, B, C or D), then "sure" or "not sure".',
    needLetter: 'Type the letter of your answer (A, B, C or D).',
    needStep: 'Type the number of the wrong step, then why. Example: "2 because…"',
    withheld: '_(Message withheld: the safety checks did not pass.)_',
    correct: 'Correct', wrong: 'Not correct', newSession: 'New session', outcome: 'Outcome', nextStep: 'Next step',
    found: 'Misconception found',
    sources: 'Sources',
  },
}

let counter = 0
const uid = () => `t${Date.now().toString(36)}${(counter++).toString(36)}`
const msg = (role: 'user' | 'assistant', text: string): UIMessage =>
  ({ id: uid(), role, parts: [{ type: 'text', text }] }) as UIMessage

// LaTeX subset of the bank -> readable text (the chat renders Markdown without a maths renderer)
export function latexToText(s: string): string {
  let t = s.replace(/\\\(|\\\)/g, ' ')
  for (let i = 0; i < 3; i++) t = t.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '($1)/($2)')
  t = t
    .replace(/\\times/g, '×')
    .replace(/\\div/g, '÷')
    .replace(/\\square/g, '□')
    .replace(/\\[a-zA-Z]+/g, ' ')
    .replace(/\((-?\d+(?:\.\d+)?)\)\/\((\d+)\)/g, '$1/$2')
  return t.replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, ' ').trim()
}

function safe(t: SafeText | null | undefined, lang: Lang) {
  if (!t) return ''
  return t.shown_allowed ? t.text : T[lang].withheld
}

function renderQuestion(q: QuestionView) {
  const opts = Object.entries(q.options).map(([k, v]) => `- **${k}.** ${latexToText(v)}`)
  return `**${latexToText(q.text)}**\n\n${opts.join('\n')}`
}

function renderTurn(turn: Turn, lang: Lang) {
  const L = T[lang]
  const parts: string[] = []
  if (turn.grading && turn.grading.method !== 'none' && turn.grading.correct !== null) {
    parts.push(`_${turn.grading.correct ? L.correct : L.wrong} · ${turn.grading.label}_`)
  }
  parts.push(safe(turn.message, lang).replace(/\n/g, '  \n'))
  if (turn.reconstruction) {
    const r = turn.reconstruction
    parts.push(`**${r.problem}**\n\n${r.steps.map((s, i) => `${i + 1}. ${s}`).join('\n')}`)
  }
  if (turn.question) parts.push(renderQuestion(turn.question))
  if (turn.state !== 'DIAGNOSE' && turn.expects !== 'none' && turn.agenda) {
    parts.push(`_${L.step} ${turn.agenda.step} ${L.of} ${turn.agenda.total} · ${L.next} : ${turn.agenda.next}_`)
  }
  return parts.filter(Boolean).join('\n\n')
}

function renderChat(a: ChatAnswer, lang: Lang) {
  const seen = new Set<string>()
  const src = a.citations
    .map((c) => `${c.file.split('/').pop()}, p. ${c.page}`)
    .filter((s) => (seen.has(s) ? false : (seen.add(s), true)))
  const label = a.label ? `\n\n_${a.label}_` : ''
  return safe(a.answer, lang).replace(/\n/g, '  \n') + label + (src.length ? `\n\n_${T[lang].sources} : ${src.join(' · ')}_` : '')
}

// a free question (not an answer to the current step): sent to the course chat
function looksLikeQuestion(text: string) {
  return /[?؟]/.test(text) || text.trim().split(/\s+/).length >= 4
}

// "A sûr, parce que…" -> option, confidence, explanation
function parseAnswer(text: string) {
  const m = text.match(/^\s*\(?([A-Da-d])(?=[\s).,:;\-·]|$)/)
  if (!m) return null
  let rest = text.slice(m[0].length)
  let confidence: 'sure' | 'unsure' | null = null
  const unsure = rest.match(/(pas\s*s[uû]re?|not\s*sure|unsure|غير\s*متأك+ّ?د)/i)
  const sure = rest.match(/(s[uû]re?|sure|متأك+ّ?د)/i)
  if (unsure) {
    confidence = 'unsure'
    rest = rest.replace(unsure[0], ' ')
  } else if (sure) {
    confidence = 'sure'
    rest = rest.replace(sure[0], ' ')
  }
  const explanation = rest.replace(/^[\s).,:;\-·]+/, '').trim()
  return { option: m[1].toUpperCase(), confidence, explanation }
}

async function engine<T>(body: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
  const r = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const e = new Error(typeof data.detail === 'string' ? data.detail : `engine error ${r.status}`) as Error & { status?: number }
    e.status = r.status
    throw e
  }
  return data as T
}

type Opts = {
  id: string
  messages: UIMessage[]
  lang: Lang
  student: { name: string; level: string }
  startText?: string // the "start the diagnosis" button text; any other free text goes to the course chat
}

export function useTraceChat({ id, messages: initial, lang, student, startText }: Opts) {
  const [messages, setMessages] = useState<UIMessage[]>(initial)
  const [status, setStatus] = useState<'ready' | 'submitted' | 'streaming'>('ready')
  const [error, setError] = useState<Error | undefined>()
  const [pending, setPending] = useState<Pending | null>(() => SESSIONS.get(id)?.pending ?? null)
  const abort = useRef<AbortController | null>(null)
  const lastText = useRef<string | null>(null)
  const L = T[lang]

  const store = (patch: Partial<Stored>) => {
    const cur = SESSIONS.get(id) ?? { sessionId: null, pending: null }
    const next = { ...cur, ...patch }
    SESSIONS.set(id, next)
    if ('pending' in patch) setPending(next.pending)
  }

  const run = useCallback(
    async (text: string, addUser: boolean) => {
      lastText.current = text
      if (addUser) setMessages((m) => [...m, msg('user', text)])
      setError(undefined)
      setStatus('submitted')
      const ctrl = new AbortController()
      abort.current = ctrl
      const say = (t: string) => setMessages((m) => [...m, msg('assistant', t)])
      try {
        const cur = SESSIONS.get(id)
        const start = async () => {
          const s = await engine<SessionState>(
            { action: 'start', student: { ...student, lang }, profile: PROFILE, demo: DEMO },
            ctrl.signal,
          )
          store({ sessionId: s.session_id, pending: { expects: 'answer', question: s.current_question, steps: 0 } })
          const warn = s.warnings.length ? `\n\n_${s.warnings.join(' ')}_` : ''
          say(`${L.intro}${warn}\n\n${s.current_question ? renderQuestion(s.current_question) : ''}`)
        }
        const ask = async () => {
          const r = await engine<ChatAnswer>({ action: 'ask', question: text, lang, sessionId: cur?.sessionId ?? null }, ctrl.signal)
          say(renderChat(r, lang))
        }
        const active = !!(cur?.sessionId && cur.pending && cur.pending.expects !== 'none')
        if (!active) {
          if (text === startText || text === L.newSession) await start()
          else await ask() // free question: course chat (citations) or polite refusal, decided by the engine
          return
        }
        const p = cur!.pending!
        let turn: Turn
        if (p.expects === 'answer') {
          const a = parseAnswer(text)
          if (!a || !a.confidence || !p.question || !(a.option in p.question.options)) {
            if (!a && looksLikeQuestion(text)) await ask()
            else say(L.needOption)
            return
          }
          turn = await engine<Turn>(
            {
              action: 'answer', sessionId: cur!.sessionId, question_id: p.question.id, option: a.option,
              confidence: a.confidence, explanation: a.explanation || null,
            },
            ctrl.signal,
          )
        } else if (p.expects === 'error_step') {
          const m = text.match(/(\d+)/)
          if (!m || Number(m[1]) < 1 || Number(m[1]) > p.steps) {
            say(L.needStep)
            return
          }
          const why = text.replace(m[0], ' ').replace(/^[\s).,:;\-·]*(étape|step|الخطوة)?[\s).,:;\-·]*/i, '').trim()
          turn = await engine<Turn>({ action: 'reply', sessionId: cur!.sessionId, choice: m[1], text: why || null }, ctrl.signal)
        } else {
          const a = parseAnswer(text)
          if (!a || (p.question && !(a.option in p.question.options))) {
            if (!a && looksLikeQuestion(text)) await ask()
            else say(L.needLetter)
            return
          }
          turn = await engine<Turn>({ action: 'reply', sessionId: cur!.sessionId, choice: a.option }, ctrl.signal)
        }
        store({
          pending: {
            expects: turn.expects,
            question: turn.question,
            steps: turn.reconstruction?.steps.length ?? 0,
          },
        })
        say(renderTurn(turn, lang))
        if (turn.expects === 'none') {
          const s = await engine<Summary>({ action: 'summary', sessionId: cur!.sessionId }, ctrl.signal)
          const nameKey = lang === 'fr' ? 'name_fr' : lang === 'ar' ? 'name_ar' : 'name_en'
          say(
            `**${L.found} :** ${s.diagnosis_names[nameKey] || s.diagnosis_names.name_en}\n\n` +
              `**${L.outcome} :** ${safe(s.outcome, lang)}\n\n**${L.nextStep} :** ${safe(s.next_step, lang)}`,
          )
        }
      } catch (e) {
        const err = e as Error & { status?: number; name?: string }
        if (err.name === 'AbortError') return
        if (err.status === 404) store({ sessionId: null, pending: null }) // engine restarted: next message starts again
        setError(err)
      } finally {
        setStatus('ready')
        abort.current = null
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [id, lang, student.name, student.level],
  )

  const sendMessage = useCallback(({ text }: { text: string }) => run(text, true), [run])
  const stop = useCallback(() => abort.current?.abort(), [])
  const regenerate = useCallback(() => {
    if (lastText.current !== null) run(lastText.current, false)
  }, [run])

  // shortcut replies for the current step (rendered with the existing suggestion-chip style)
  const quickReplies: string[] = (() => {
    if (!pending) return []
    if (pending.expects === 'answer' && pending.question) {
      return Object.keys(pending.question.options).flatMap((k) => [`${k} ${L.sure}`, `${k} ${L.unsure}`])
    }
    if ((pending.expects === 'retry' || pending.expects === 'transfer_answer') && pending.question) {
      return Object.keys(pending.question.options)
    }
    if (pending.expects === 'error_step') return Array.from({ length: pending.steps }, (_, i) => `${L.step} ${i + 1}`)
    if (pending.expects === 'none') return [L.newSession]
    return []
  })()

  return { messages, sendMessage, status, stop, error, regenerate, quickReplies }
}
