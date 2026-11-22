'use client'

// Practice quiz player: one question at a time, answer checked by the TRACE engine (the key stays on the server),
// explanation, next question, final score. Questions and explanations arrive checked by the engine's guards.
import { useState } from 'react'
import { ArrowLeft, ArrowRight, Check, RotateCcw, Trophy, X } from 'lucide-react'
import type { Lang } from '@/lib/translations'
import { MathText } from './math-text'
import { cn } from '@/lib/utils'

type SafeText = { text: string; shown_allowed: boolean }
export type PracticeQuiz = {
  quiz_id: string
  questions: { id: string; question: SafeText; options: Record<string, SafeText>; sources: { file: string; page: number | null }[] }[]
  verification: string
  refused: string | null
}
type Check = { correct: boolean; correct_option: string; explanation: SafeText }

const COPY: Record<Lang, Record<string, string>> = {
  en: { question: 'Question', of: 'of', next: 'Next question', finish: 'See my score', correct: 'Correct', wrong: 'Not quite', answer: 'Correct answer', score: 'Your score', restart: 'Try again', back: 'Back', page: 'p.', checking: 'Checking…', error: 'The answer could not be checked. Try again.', great: 'Very good work.', ok: 'Good. Review the questions you missed.', low: 'Review the course, then try again.' },
  fr: { question: 'Question', of: 'sur', next: 'Question suivante', finish: 'Voir mon score', correct: 'Bonne réponse', wrong: 'Pas tout à fait', answer: 'Bonne réponse', score: 'Ton score', restart: 'Recommencer', back: 'Retour', page: 'p.', checking: 'Vérification…', error: 'La réponse n’a pas pu être vérifiée. Réessaie.', great: 'Très bon travail.', ok: 'Bien. Revois les questions manquées.', low: 'Relis le cours, puis réessaie.' },
  ar: { question: 'السؤال', of: 'من', next: 'السؤال التالي', finish: 'اعرض نتيجتي', correct: 'إجابة صحيحة', wrong: 'ليس تمامًا', answer: 'الإجابة الصحيحة', score: 'نتيجتك', restart: 'أعد المحاولة', back: 'رجوع', page: 'ص.', checking: 'جارٍ التحقّق…', error: 'تعذّر التحقّق من الإجابة. حاول مجددًا.', great: 'عمل جيّد جدًا.', ok: 'جيّد. راجع الأسئلة التي أخطأت فيها.', low: 'راجع الدرس ثم حاول مجددًا.' },
}
const shown = (s?: SafeText | null) => (s && s.shown_allowed ? s.text : '')

export function QuizPlayer({ quiz, lang, onExit }: { quiz: PracticeQuiz; lang: Lang; onExit: () => void }) {
  const c = COPY[lang]
  const [index, setIndex] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)
  const [result, setResult] = useState<Check | null>(null)
  const [score, setScore] = useState(0)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const total = quiz.questions.length
  const q = quiz.questions[index]

  async function choose(letter: string) {
    if (result || busy) return
    setPicked(letter)
    setBusy(true)
    setError(null)
    try {
      const r = await fetch(`/engine/practice/quiz/${encodeURIComponent(quiz.quiz_id)}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: q.id, option: letter }),
      })
      if (!r.ok) throw new Error(String(r.status))
      const data = (await r.json()) as Check
      setResult(data)
      if (data.correct) setScore((s) => s + 1)
    } catch {
      setPicked(null)
      setError(c.error)
    } finally {
      setBusy(false)
    }
  }

  function next() {
    if (index + 1 >= total) {
      setDone(true)
      return
    }
    setIndex((i) => i + 1)
    setPicked(null)
    setResult(null)
  }

  function restart() {
    setIndex(0)
    setPicked(null)
    setResult(null)
    setScore(0)
    setDone(false)
  }

  const header = (
    <button type="button" onClick={onExit} className="inline-flex min-h-10 items-center gap-2 self-start rounded-lg px-2 text-sm font-semibold text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <ArrowLeft className="size-4 rtl:rotate-180" aria-hidden="true" />
      {c.back}
    </button>
  )

  if (done) {
    const pct = total ? Math.round((score / total) * 100) : 0
    return (
      <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12" aria-labelledby="quiz-score">
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
          {header}
          <div className="flex flex-col items-center rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
            <span className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-secondary text-primary">
              <Trophy className="size-8" aria-hidden="true" />
            </span>
            <h1 id="quiz-score" className="text-2xl font-bold text-foreground">{c.score}</h1>
            <p className="mt-2 text-5xl font-bold tabular-nums text-primary">{score} / {total}</p>
            <div className="mt-5 h-3 w-full max-w-sm overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
              <div className="h-full rounded-full bg-gradient-to-r from-primary to-brand-cyan" style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-4 text-muted-foreground">{pct >= 80 ? c.great : pct >= 50 ? c.ok : c.low}</p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <button type="button" onClick={restart} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-border px-5 py-2.5 font-semibold text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <RotateCcw className="size-4" aria-hidden="true" />
                {c.restart}
              </button>
              <button type="button" onClick={onExit} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {c.back}
              </button>
            </div>
          </div>
          <p className="text-center text-xs text-muted-foreground">{quiz.verification}</p>
        </div>
      </section>
    )
  }

  return (
    <section className="min-h-[calc(100dvh-5rem)] bg-muted/40 px-4 py-8 md:px-8 md:py-12" aria-labelledby="quiz-question">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        {header}
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-muted-foreground tabular-nums">{c.question} {index + 1} {c.of} {total}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={index + (result ? 1 : 0)}>
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-brand-cyan transition-[width] duration-300" style={{ width: `${((index + (result ? 1 : 0)) / total) * 100}%` }} />
          </div>
        </div>

        <div className="rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-8">
          <h1 id="quiz-question" className="text-balance text-xl font-bold leading-snug text-foreground sm:text-2xl"><MathText text={shown(q.question)} /></h1>
          {q.sources[0]?.page ? <p className="mt-2 text-xs text-muted-foreground">{q.sources[0].file} · {c.page} {q.sources[0].page}</p> : null}

          <ul className="mt-6 flex flex-col gap-3">
            {Object.entries(q.options).map(([letter, opt]) => {
              const isPicked = picked === letter
              const isCorrect = result && result.correct_option === letter
              const isWrong = result && isPicked && !result.correct
              return (
                <li key={letter}>
                  <button
                    type="button"
                    disabled={!!result || busy}
                    onClick={() => choose(letter)}
                    className={cn(
                      'flex w-full items-center gap-4 rounded-2xl border px-4 py-3.5 text-start transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      !result && 'border-border bg-background/70 hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md',
                      !result && isPicked && 'border-primary',
                      isCorrect && 'border-primary bg-secondary',
                      isWrong && 'border-destructive/50 bg-destructive/10',
                      result && !isCorrect && !isWrong && 'border-border bg-background/40 opacity-70',
                    )}
                  >
                    <span className={cn('flex size-9 shrink-0 items-center justify-center rounded-xl text-sm font-bold', isCorrect ? 'bg-primary text-primary-foreground' : isWrong ? 'bg-destructive text-primary-foreground' : 'bg-muted text-foreground')}>
                      {isCorrect ? <Check className="size-4" aria-hidden="true" /> : isWrong ? <X className="size-4" aria-hidden="true" /> : letter}
                    </span>
                    <span className="flex-1 text-base text-foreground"><MathText text={shown(opt)} /></span>
                  </button>
                </li>
              )
            })}
          </ul>

          {busy ? <p className="mt-4 text-sm text-muted-foreground" role="status">{c.checking}</p> : null}
          {error ? <p className="mt-4 text-sm text-destructive" role="alert">{error}</p> : null}

          {result ? (
            <div className={cn('mt-6 rounded-2xl border p-4', result.correct ? 'border-primary/40 bg-secondary/60' : 'border-destructive/30 bg-destructive/10')} role="status">
              <p className={cn('font-semibold', result.correct ? 'text-primary-deep' : 'text-destructive')}>
                {result.correct ? c.correct : `${c.wrong} · ${c.answer} : ${result.correct_option}`}
              </p>
              {shown(result.explanation) ? <p className="mt-1 text-sm text-foreground"><MathText text={shown(result.explanation)} /></p> : null}
            </div>
          ) : null}

          {result ? (
            <div className="mt-6 flex justify-end">
              <button type="button" onClick={next} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition hover:bg-primary-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                {index + 1 >= total ? c.finish : c.next}
                <ArrowRight className="size-4 rtl:rotate-180" aria-hidden="true" />
              </button>
            </div>
          ) : null}
        </div>
        <p className="text-center text-xs text-muted-foreground">{quiz.verification}</p>
      </div>
    </section>
  )
}
