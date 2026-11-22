'use client'

// Interactive lesson built from the demo course "cours_fractions_relatifs.pdf" (4 pages of original notes written by
// the TRACE team). Every rule, example and common mistake comes from those pages (cited "p. N"); every number shown
// and every answer key is COMPUTED by fraction-math.ts (exact integers). Learning cycle: observe (3D solid) ->
// explore (manipulate bars, denominators, number line) -> understand (rules) -> apply (sorting, find A) ->
// evaluate (questions with feedback and retries) -> summary.
import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Award, Box, Check, ChevronRight, CircleHelp, Eye, Lightbulb, RotateCcw, Sparkles, Target, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MathText } from '../math-text'
import { FractionCake3D, FractionDisc, webglOk } from './fraction-cake-3d'
import { FractionBar, NumberLine } from './lesson-visuals'
import { add, equal, fmt, less, mixed, mulInt, parse, simplify, type Frac } from './fraction-math'

export const FRACTION_SECTIONS = [
  { id: 'intro', letter: 'A', title: 'Introduction' },
  { id: 'discover', letter: 'B', title: 'Découverte' },
  { id: 'explore', letter: 'C', title: 'Exploration' },
  { id: 'rules', letter: 'D', title: 'Les règles' },
  { id: 'practice', letter: 'E', title: 'Pratique' },
  { id: 'check', letter: 'F', title: 'Vérification' },
  { id: 'summary', letter: 'G', title: 'Résumé' },
] as const

const Page = ({ n }: { n: number }) => <span className="ms-1.5 inline-flex shrink-0 whitespace-nowrap rounded-full bg-secondary px-2 py-0.5 align-middle text-[11px] font-bold text-primary-deep">p. {n}</span>

function Section({ id, letter, title, kicker, children }: { id: string; letter: string; title: string; kicker: string; children: React.ReactNode }) {
  return (
    <motion.section id={`lesson-${id}`} className="scroll-mt-28" initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: '-80px' }} transition={{ duration: 0.5 }}>
      <div className="mb-4 flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-2xl bg-primary text-lg font-extrabold text-primary-foreground">{letter}</span>
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-primary">{kicker}</p>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">{title}</h2>
        </div>
      </div>
      {children}
    </motion.section>
  )
}

const Card = ({ className, children }: { className?: string; children: React.ReactNode }) => (
  <div className={cn('rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-7', className)}>{children}</div>
)

function Feedback({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} role="status"
      className={cn('mt-4 flex items-start gap-3 rounded-2xl p-4 text-sm leading-relaxed', ok ? 'bg-emerald-500/12 text-foreground' : 'bg-rose-500/12 text-foreground')}>
      <span className={cn('flex size-6 shrink-0 items-center justify-center rounded-full text-white', ok ? 'bg-emerald-500' : 'bg-rose-500')}>{ok ? <Check className="size-4" /> : <X className="size-4" />}</span>
      <div>{children}</div>
    </motion.div>
  )
}

function Slider({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <label className="flex flex-col gap-2 text-sm font-semibold text-foreground">
      <span className="flex items-center justify-between">{label}<span className="rounded-lg bg-muted px-2 py-0.5 tabular-nums">{value}</span></span>
      <input type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} className="accent-[var(--color-primary)]" />
    </label>
  )
}

// ---------------------------------------------------------------- A. introduction: the 3D fraction cake
function Intro({ reduced, onDone }: { reduced: boolean; onDone: () => void }) {
  const [den, setDen] = useState(8)
  const [num, setNum] = useState(3)
  const [gl, setGl] = useState(false)
  useEffect(() => setGl(webglOk()), [])
  useEffect(() => { if (num !== 3 || den !== 8) onDone() }, [num, den, onDone])
  const f = simplify({ n: num, d: den })
  return (
    <div className="grid gap-5 lg:grid-cols-[1.15fr_1fr]">
      <Card className="flex flex-col gap-4 bg-gradient-to-br from-primary/10 via-card to-brand-cyan/10">
        <p className="text-lg leading-relaxed text-foreground">
          On partage un gâteau en <b>{den}</b> parts égales et on en colore <b>{num}</b>. Quelle part du gâteau est colorée ?
          C’est exactement ce que dit la fraction <MathText text={`${num}/${den}`} />.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Slider label="Parts égales (dénominateur)" value={den} min={2} max={12} onChange={(v) => { setDen(v); setNum((n) => Math.min(n, v)) }} />
          <Slider label="Parts colorées (numérateur)" value={num} min={0} max={den} onChange={setNum} />
        </div>
        <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-background/80 p-4">
          <span className="text-3xl font-extrabold text-primary"><MathText text={`${num}/${den}`} /></span>
          <span className="text-sm text-muted-foreground">
            {num === 0 ? 'Aucune part colorée : 0.' : num === den ? `Tout le gâteau est coloré : ${num}/${den} = 1.` : f.d !== den ? <>Même quantité que <MathText text={fmt(f)} /> : on le verra en partie B.</> : 'du gâteau est colorée.'}
          </span>
        </div>
        <ul className="grid gap-2 sm:grid-cols-2">
          {[['Additionner des fractions', 1], ['Multiplier par un entier', 2], ['Soustraire un nombre négatif', 3], ['Reconnaître des fractions égales', 4]].map(([t, p]) => (
            <li key={t} className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm font-semibold text-foreground"><Target className="size-4 shrink-0 text-primary" />{t}<Page n={p as number} /></li>
          ))}
        </ul>
      </Card>
      <div className="flex flex-col gap-2">
        {gl ? <FractionCake3D num={num} den={den} height={340} reduced={reduced} label={`Gâteau en 3D : ${num} parts colorées sur ${den}`} />
          : <div className="flex h-[340px] items-center justify-center rounded-3xl bg-secondary/50"><FractionDisc num={num} den={den} size={240} label={`${num} parts colorées sur ${den}`} /></div>}
        <p className="flex items-center gap-2 text-xs text-muted-foreground"><Box className="size-3.5" />{gl ? 'Cylindre en 3D : fais-le tourner avec la souris. Les parts ont toutes le même volume.' : 'Vue à plat (WebGL indisponible).'}</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- B. discovery: equal fractions (p. 4)
function Discover({ onDone }: { onDone: () => void }) {
  const [k, setK] = useState(1)
  const [wrongWay, setWrongWay] = useState(false)
  useEffect(() => { if (k > 1) onDone() }, [k, onDone])
  const base: Frac = { n: 3, d: 5 }
  const big: Frac = { n: base.n * k, d: base.d * k }
  const bad: Frac = { n: 9 - 5, d: 15 - 5 } // the mistake described on p. 4
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <h3 className="font-bold text-foreground">Multiplie le haut ET le bas par le même nombre<Page n={4} /></h3>
        <div className="mt-4"><Slider label="Multiplier par" value={k} min={1} max={4} onChange={setK} /></div>
        <div className="mt-5 flex flex-col gap-3">
          <div className="flex items-center gap-3"><span className="w-16 text-end font-bold"><MathText text="3/5" /></span><FractionBar num={3} den={5} label="3/5" /></div>
          <div className="flex items-center gap-3"><span className="w-16 text-end font-bold text-brand-cyan"><MathText text={fmt(big)} /></span><FractionBar num={big.n} den={big.d} color="var(--color-brand-cyan, #3a9ad9)" label={fmt(big)} /></div>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-foreground">
          {k === 1 ? 'Bouge le curseur : les parts deviennent plus petites, mais la longueur colorée ne change pas.' : <>Les deux barres ont la même longueur colorée : <MathText text={`3/5 = ${fmt(big)}`} />. On a multiplié le numérateur et le dénominateur par {k}.</>}
        </p>
      </Card>
      <Card>
        <h3 className="font-bold text-foreground">Le piège : ajouter ou enlever le même nombre<Page n={4} /></h3>
        <p className="mt-2 text-sm text-muted-foreground">Partons de <MathText text="9/15" />. Que se passe-t-il si on enlève 5 en haut et en bas ?</p>
        <button type="button" onClick={() => setWrongWay(true)} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl border border-border px-4 text-sm font-semibold hover:border-primary/50 hover:text-primary"><Eye className="size-4" />Montrer</button>
        <AnimatePresence>
          {wrongWay ? (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="overflow-hidden">
              <div className="mt-4 flex flex-col gap-3">
                <div className="flex items-center gap-3"><span className="w-16 text-end font-bold"><MathText text="9/15" /></span><FractionBar num={9} den={15} label="9/15" /></div>
                <div className="flex items-center gap-3"><span className="w-16 text-end font-bold text-rose-500"><MathText text={fmt(bad)} /></span><FractionBar num={bad.n} den={bad.d} color="#f43f5e" label={fmt(bad)} /></div>
              </div>
              <Feedback ok={false}>
                <MathText text={`9 - 5 = 4 et 15 - 5 = 10 donne 4/10. Mais 4/10 = ${fmt(simplify(bad))} et 9/15 = ${fmt(simplify({ n: 9, d: 15 }))} : les longueurs colorées sont différentes.`} />
                {' '}On ne doit jamais ajouter ou enlever : on multiplie ou on divise.
              </Feedback>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- C1. addition 1/3 + 2/5 (p. 1)
function AddExplorer({ onDone }: { onDone: () => void }) {
  const a: Frac = { n: 1, d: 3 }, b: Frac = { n: 2, d: 5 }
  const [d, setD] = useState<number | null>(null)
  const sum = add(a, b)
  const fits = d !== null && d % a.d === 0 && d % b.d === 0
  useEffect(() => { if (fits) onDone() }, [fits, onDone])
  const wrong: Frac = { n: a.n + b.n, d: a.d + b.d } // the mistake on p. 1
  return (
    <Card>
      <h3 className="font-bold text-foreground">Additionner <MathText text="1/3 + 2/5" /> : choisis un dénominateur commun<Page n={1} /></h3>
      <div className="mt-4 flex flex-wrap gap-2">
        {[5, 8, 10, 12, 15, 30].map((v) => (
          <button key={v} type="button" aria-pressed={d === v} onClick={() => setD(v)} className={cn('min-h-10 min-w-12 rounded-xl border px-3 font-bold transition', d === v ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background hover:border-primary/50')}>{v}</button>
        ))}
      </div>
      {d !== null ? (
        <div className="mt-5 flex flex-col gap-3">
          <div className="flex items-center gap-3"><span className="w-20 text-end font-bold"><MathText text="1/3" /></span><FractionBar num={1} den={3} label="1/3" /></div>
          <div className="flex items-center gap-3"><span className="w-20 text-end font-bold"><MathText text="2/5" /></span><FractionBar num={2} den={5} label="2/5" /></div>
          {fits ? (
            <>
              <div className="flex items-center gap-3"><span className="w-20 text-end font-bold text-emerald-600"><MathText text={`${(a.n * d) / a.d + (b.n * d) / b.d}/${d}`} /></span><FractionBar num={(a.n * d) / a.d + (b.n * d) / b.d} den={d} color="#10b981" label="somme" /></div>
              <Feedback ok>
                <MathText text={`1/3 = ${(a.n * d) / a.d}/${d} et 2/5 = ${(b.n * d) / b.d}/${d}, donc 1/3 + 2/5 = ${(a.n * d) / a.d + (b.n * d) / b.d}/${d}`} />
                {fmt(sum) !== `${(a.n * d) / a.d + (b.n * d) / b.d}/${d}` ? <> <MathText text={`= ${fmt(sum)}`} /></> : null}.
                {d !== 15 ? <> Ça marche, et le plus petit dénominateur commun est 15.</> : <> 15 est le plus petit dénominateur commun.</>}
              </Feedback>
            </>
          ) : d === a.d + b.d ? (
            <>
              <div className="flex items-center gap-3"><span className="w-20 text-end font-bold text-rose-500"><MathText text={fmt(wrong)} /></span><FractionBar num={wrong.n} den={wrong.d} color="#f43f5e" label={fmt(wrong)} /></div>
              <Feedback ok={false}>8 = 3 + 5 : c’est l’erreur fréquente « additionner les dénominateurs ». Regarde : <MathText text="3/8" /> est {less(wrong, b) ? 'plus petit' : 'plus grand'} que <MathText text="2/5" />, alors qu’une somme doit être plus grande que chaque fraction.<Page n={1} /></Feedback>
            </>
          ) : (
            <Feedback ok={false}>{d % a.d !== 0 ? <>On ne peut pas couper un tiers en parts de 1/{d} : {d} n’est pas un multiple de 3.</> : <>{d} n’est pas un multiple de 5 : les cinquièmes ne tombent pas juste.</>} Essaie un autre nombre.</Feedback>
          )}
        </div>
      ) : <p className="mt-4 text-sm text-muted-foreground">Un bon dénominateur commun est un multiple de 3 et de 5.</p>}
    </Card>
  )
}

// ---------------------------------------------------------------- C2. fraction × whole number (p. 2)
function MultiplyExplorer({ onDone }: { onDone: () => void }) {
  const [k, setK] = useState(1)
  useEffect(() => { if (k >= 3) onDone() }, [k, onDone])
  const base: Frac = { n: 2, d: 3 }
  const r = mulInt(base, k)
  return (
    <Card>
      <h3 className="font-bold text-foreground">Multiplier <MathText text="2/3" /> par un entier<Page n={2} /></h3>
      <div className="mt-4"><Slider label="Nombre de fois" value={k} min={1} max={6} onChange={setK} /></div>
      <div className="mt-4 flex flex-col gap-2">
        <p className="text-sm text-muted-foreground"><MathText text={Array.from({ length: k }, () => '2/3').join(' + ')} /> :</p>
        <FractionBar num={2 * k} den={3} label={`${2 * k}/3`} />
      </div>
      <div className="mt-4 rounded-2xl bg-background/80 p-4 text-base text-foreground">
        <MathText text={`2/3 × ${k} = ${2 * k}/3`} />{r.d === 1 ? <> <MathText text={`= ${r.n}`} /></> : mixed({ n: 2 * k, d: 3 }) !== `${2 * k}/3` ? <> = {mixed({ n: 2 * k, d: 3 })}</> : null}
        <p className="mt-1 text-sm text-muted-foreground">On multiplie seulement le numérateur ; le dénominateur 3 ne change pas (la taille des parts reste la même).</p>
      </div>
      {k === 5 ? <Feedback ok={false}>Erreur fréquente : multiplier aussi le dénominateur donne <MathText text="10/15" />. Or <MathText text={`10/15 = ${fmt(simplify({ n: 10, d: 15 }))}`} /> : la valeur de départ n’a pas changé, alors qu’on a multiplié par 5.<Page n={2} /></Feedback> : null}
    </Card>
  )
}

// ---------------------------------------------------------------- C3. subtracting a negative number (p. 3)
function NumberLineExplorer({ onDone }: { onDone: () => void }) {
  const [a, setA] = useState(-8)
  const [b, setB] = useState(-5)
  const [guess, setGuess] = useState('')
  const [shown, setShown] = useState(false)
  const result = a - b
  const g = parse(guess)
  const right = g !== null && g.d === 1 && g.n === result
  const show = () => { setShown(true); onDone() }
  const reset = () => { setShown(false); setGuess('') }
  const bTxt = b < 0 ? `(${b})` : `${b}`
  return (
    <Card>
      <h3 className="font-bold text-foreground">Soustraire un nombre négatif sur la droite graduée<Page n={3} /></h3>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Slider label="Départ" value={a} min={-10} max={5} onChange={(v) => { setA(v); reset() }} />
        <Slider label="Nombre enlevé" value={b} min={-6} max={6} onChange={(v) => { setB(v); reset() }} />
      </div>
      <p className="mt-4 text-center text-2xl font-bold text-foreground" dir="ltr"><MathText text={`${a < 0 ? `(${a})` : a} - ${bTxt} = ?`} /></p>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        <label className="text-sm font-semibold" htmlFor="nl-guess">Ta prédiction</label>
        <input id="nl-guess" value={guess} onChange={(e) => { setGuess(e.target.value); setShown(false) }} inputMode="numeric" dir="ltr" className="h-11 w-24 rounded-xl border border-input bg-background px-3 text-center text-lg font-bold outline-none focus:border-primary focus:ring-2 focus:ring-primary/25" />
        <button type="button" onClick={show} disabled={!guess.trim()} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 font-bold text-primary-foreground hover:bg-primary-deep disabled:opacity-50"><Sparkles className="size-4" />Vérifier sur la droite</button>
      </div>
      <div className="mt-4"><NumberLine from={a} to={result} show={shown} label={`Droite graduée de ${a} à ${result}`} /></div>
      {shown ? (
        <Feedback ok={right}>
          {right ? 'Bonne prédiction. ' : `Pas tout à fait : le résultat est ${result}. `}
          {b < 0 ? <>Enlever <MathText text={`${b}`} /> revient à ajouter son opposé <MathText text={`+${-b}`} /> : on avance de {-b} vers la droite. <MathText text={`${a < 0 ? `(${a})` : a} - (${b}) = ${a} + ${-b} = ${result}`} />.</>
            : b > 0 ? <>On enlève {b} : on recule de {b} vers la gauche. <MathText text={`${a < 0 ? `(${a})` : a} - ${b} = ${result}`} />.</> : <>Enlever 0 ne change rien.</>}
          {!right && b < 0 && g !== null && g.d === 1 && (g.n === -result || g.n === Math.abs(a) + Math.abs(b) || g.n === -(Math.abs(a) + Math.abs(b))) ? <> Attention : « moins par moins donne plus » est une règle de la <b>multiplication</b> (<MathText text="(-2) × (-3) = 6" />), pas de la soustraction.<Page n={3} /></> : null}
        </Feedback>
      ) : null}
    </Card>
  )
}

// ---------------------------------------------------------------- E. practice: sort the fractions, find A (p. 4)
const SORT = ['6/10', '9/15', '4/10', '12/20', '4/6', '30/50']
function Practice({ onDone }: { onDone: () => void }) {
  const target: Frac = { n: 3, d: 5 }
  const [placed, setPlaced] = useState<Record<string, 'eq' | 'ne'>>({})
  const [sel, setSel] = useState<string | null>(null)
  const [A, setA] = useState('')
  const [checkedA, setCheckedA] = useState(false)
  const truth = useMemo(() => Object.fromEntries(SORT.map((s) => [s, equal(parse(s)!, target) ? 'eq' : 'ne'])), []) // eslint-disable-line react-hooks/exhaustive-deps
  const allPlaced = SORT.every((s) => placed[s])
  const allRight = allPlaced && SORT.every((s) => placed[s] === truth[s])
  const aVal = parse(A)
  const aRight = aVal !== null && aVal.d === 1 && aVal.n * 15 === 9 * 10
  useEffect(() => { if (allRight && aRight && checkedA) onDone() }, [allRight, aRight, checkedA, onDone])
  const put = (s: string, bin: 'eq' | 'ne') => { setPlaced((p) => ({ ...p, [s]: bin })); setSel(null) }
  const why = (s: string) => {
    const f = parse(s)!, r = simplify(f)
    const k = f.n / r.n
    return equal(f, target) ? `${s} = ${fmt(r)} (on divise par ${k})` : `${s} = ${fmt(r)}, ce n'est pas 3/5`
  }
  const bin = (id: 'eq' | 'ne', title: string) => (
    <div onDragOver={(e) => e.preventDefault()} onDrop={(e) => { const s = e.dataTransfer.getData('text/plain'); if (s) put(s, id) }}
      onClick={() => sel && put(sel, id)} role="button" tabIndex={0} onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && sel) put(sel, id) }}
      aria-label={`Déposer dans : ${title}`}
      className={cn('flex min-h-32 flex-col gap-2 rounded-2xl border-2 border-dashed p-3 transition', sel ? 'border-primary/60 bg-primary/5' : 'border-border bg-muted/30')}>
      <p className="text-sm font-bold text-foreground">{title}</p>
      <div className="flex flex-wrap gap-2">
        {SORT.filter((s) => placed[s] === id).map((s) => (
          <span key={s} className={cn('rounded-xl px-3 py-1.5 text-base font-bold', !allPlaced ? 'bg-card' : placed[s] === truth[s] ? 'bg-emerald-500/15' : 'bg-rose-500/15')}><MathText text={s} /></span>
        ))}
      </div>
    </div>
  )
  return (
    <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
      <Card>
        <h3 className="font-bold text-foreground">Range chaque fraction : égale à <MathText text="3/5" /> ou non ?<Page n={4} /></h3>
        <p className="mt-1 text-sm text-muted-foreground">Glisse une carte, ou clique dessus puis sur une boîte (clavier : Tab puis Entrée).</p>
        <div className="mt-4 flex min-h-12 flex-wrap gap-2">
          {SORT.filter((s) => !placed[s]).map((s) => (
            <button key={s} type="button" draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', s)}
              onClick={() => setSel(sel === s ? null : s)} aria-pressed={sel === s}
              className={cn('cursor-grab rounded-xl border px-4 py-2 text-lg font-bold shadow-sm transition', sel === s ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background hover:border-primary/50')}>
              <MathText text={s} />
            </button>
          ))}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">{bin('eq', 'Égale à 3/5')}{bin('ne', 'Pas égale à 3/5')}</div>
        {allPlaced ? (
          <Feedback ok={allRight}>
            {allRight ? 'Tout est bien rangé.' : 'Certaines cartes sont mal rangées (en rouge).'}
            <ul className="mt-2 list-disc ps-5">{SORT.map((s) => <li key={s}><MathText text={why(s)} /></li>)}</ul>
            {!allRight ? <button type="button" onClick={() => setPlaced({})} className="mt-2 inline-flex items-center gap-1.5 font-semibold text-primary hover:underline"><RotateCcw className="size-4" />Recommencer</button> : null}
          </Feedback>
        ) : null}
      </Card>
      <Card>
        <h3 className="font-bold text-foreground">Trouve A<Page n={4} /></h3>
        <p className="mt-4 text-center text-2xl font-bold" dir="ltr"><MathText text="A/10 = 9/15" /></p>
        <div className="mt-4 flex items-center justify-center gap-2">
          <label htmlFor="find-a" className="font-bold">A =</label>
          <input id="find-a" value={A} onChange={(e) => { setA(e.target.value); setCheckedA(false) }} inputMode="numeric" dir="ltr" className="h-11 w-20 rounded-xl border border-input bg-background text-center text-lg font-bold outline-none focus:border-primary focus:ring-2 focus:ring-primary/25" />
          <button type="button" onClick={() => setCheckedA(true)} disabled={!A.trim()} className="min-h-11 rounded-xl bg-primary px-4 font-bold text-primary-foreground hover:bg-primary-deep disabled:opacity-50">Vérifier</button>
        </div>
        {checkedA ? (
          <Feedback ok={aRight}>
            {aRight ? <MathText text="Oui : 9/15 = 3/5 (on divise par 3), puis 3/5 = 6/10 (on multiplie par 2). Donc A = 6." />
              : <>Indice : simplifie d’abord <MathText text="9/15" /> (divise par 3), puis multiplie pour obtenir un dénominateur 10.</>}
          </Feedback>
        ) : null}
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- F. knowledge check (keys computed)
type Q = { q: string; value: Frac; options: string[]; why: string; trap: Record<string, string>; page: number }
const QUESTIONS: Q[] = [
  { q: '2/7 + 1/7 = ?', value: add({ n: 2, d: 7 }, { n: 1, d: 7 }), options: ['3/14', '3/7', '2/49', '1/7'], why: 'Les dénominateurs sont déjà égaux : on additionne seulement les numérateurs, 2/7 + 1/7 = 3/7.', trap: { '3/14': 'Tu as additionné les dénominateurs : on ne le fait jamais.' }, page: 1 },
  { q: '1/6 × 6 = ?', value: mulInt({ n: 1, d: 6 }, 6), options: ['6/36', '1/36', '1', '7/6'], why: 'On multiplie seulement le numérateur : 1/6 × 6 = 6/6 = 1.', trap: { '6/36': 'Tu as aussi multiplié le dénominateur : 6/36 = 1/6, la valeur n’a pas changé.' }, page: 2 },
  { q: '(−3) − 5 = ?', value: { n: -3 - 5, d: 1 }, options: ['−2', '2', '−8', '8'], why: 'On part de −3 et on enlève 5 : on recule de 5 vers la gauche, on arrive à −8.', trap: { '2': 'Attention au sens : enlever 5 fait reculer vers la gauche.', '8': '« Moins par moins donne plus » concerne la multiplication, pas la soustraction.' }, page: 3 },
  { q: '1/3 + 2/5 = ?', value: add({ n: 1, d: 3 }, { n: 2, d: 5 }), options: ['3/8', '3/15', '11/15', '2/15'], why: 'Dénominateur commun 15 : 1/3 = 5/15 et 2/5 = 6/15, donc 11/15.', trap: { '3/8': '3/8 est plus petit que 2/5 : une somme doit être plus grande que chaque fraction.' }, page: 1 },
]

function Check4({ onDone }: { onDone: (score: number) => void }) {
  const [answers, setAnswers] = useState<(string | null)[]>(QUESTIONS.map(() => null))
  const [firstTry, setFirstTry] = useState<(boolean | null)[]>(QUESTIONS.map(() => null))
  const isRight = (qi: number, o: string) => { const f = parse(o); return f !== null && equal(f, QUESTIONS[qi].value) }
  const done = answers.every((a, i) => a !== null && isRight(i, a))
  useEffect(() => { if (done) onDone(firstTry.filter(Boolean).length) }, [done]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {QUESTIONS.map((q, qi) => {
        const a = answers[qi]
        const ok = a !== null && isRight(qi, a)
        return (
          <Card key={q.q}>
            <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-primary"><CircleHelp className="size-4" />Question {qi + 1}<Page n={q.page} /></p>
            <p className="mt-2 text-2xl font-bold text-foreground" dir="ltr"><MathText text={q.q} /></p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              {q.options.map((o) => (
                <button key={o} type="button" disabled={ok} onClick={() => { setAnswers((s) => s.map((x, i) => (i === qi ? o : x))); setFirstTry((s) => s.map((x, i) => (i === qi && x === null ? isRight(qi, o) : x))) }}
                  className={cn('min-h-12 rounded-xl border text-lg font-bold transition', a === o ? (isRight(qi, o) ? 'border-emerald-500 bg-emerald-500/15' : 'border-rose-500 bg-rose-500/15') : 'border-border bg-background hover:border-primary/50', ok && a !== o && 'opacity-50')}>
                  <MathText text={o.replace(/−/g, '-')} />
                </button>
              ))}
            </div>
            {a !== null ? (
              <Feedback ok={ok}>
                {ok ? <MathText text={q.why} /> : <>{q.trap[a] ?? 'Ce n’est pas la bonne réponse.'} Réessaie.</>}
              </Feedback>
            ) : null}
          </Card>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------- the whole lesson
export function FractionsLesson({ reduced, onProgress }: { reduced: boolean; onProgress: (done: Set<string>, score: number | null) => void }) {
  const [done, setDone] = useState<Set<string>>(new Set())
  const [score, setScore] = useState<number | null>(null)
  const mark = useMemo(() => {
    const cache: Record<string, () => void> = {}
    return (k: string) => (cache[k] ??= () => setDone((s) => (s.has(k) ? s : new Set(s).add(k))))
  }, [])
  useEffect(() => onProgress(done, score), [done, score, onProgress])

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-14 px-4 pb-24 pt-8 md:px-8">
      <header className="relative overflow-hidden rounded-[2rem] border border-border bg-gradient-to-br from-primary/15 via-card to-brand-cyan/15 p-7 sm:p-10">
        <motion.div className="absolute -end-16 -top-16 size-56 rounded-full bg-primary/20 blur-3xl" animate={reduced ? undefined : { scale: [1, 1.15, 1] }} transition={{ duration: 8, repeat: Infinity }} />
        <p className="relative inline-flex items-center gap-2 rounded-full bg-background/80 px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-primary-deep"><Sparkles className="size-4" />Leçon interactive · cours_fractions_relatifs.pdf</p>
        <h1 className="relative mt-4 max-w-3xl text-balance text-4xl font-bold leading-tight tracking-tight text-foreground sm:text-5xl">Fractions et nombres relatifs : voir, manipuler, comprendre</h1>
        <p className="relative mt-3 max-w-2xl text-lg text-muted-foreground">Quatre règles du cours, à découvrir en les manipulant. Chaque résultat est calculé, chaque règle renvoie à sa page.</p>
      </header>

      <Section id="intro" letter="A" title="Une fraction, c’est une part d’un tout" kicker="Introduction · observer"><Intro reduced={reduced} onDone={mark('intro')} /></Section>
      <Section id="discover" letter="B" title="Des fractions différentes, la même quantité" kicker="Découverte"><Discover onDone={mark('discover')} /></Section>
      <Section id="explore" letter="C" title="Expérimente les trois opérations" kicker="Exploration">
        <div className="flex flex-col gap-5">
          <AddExplorer onDone={mark('add')} />
          <MultiplyExplorer onDone={mark('mul')} />
          <NumberLineExplorer onDone={mark('line')} />
        </div>
      </Section>
      <Section id="rules" letter="D" title="Ce qu’il faut retenir" kicker="Comprendre">
        <div className="grid gap-4 md:grid-cols-2">
          {[
            { t: 'Additionner des fractions', p: 1, r: 'Même dénominateur d’abord, puis on additionne les numérateurs. On n’additionne jamais les dénominateurs.', ex: '1/3 + 2/5 = 5/15 + 6/15 = 11/15' },
            { t: 'Multiplier par un entier', p: 2, r: 'On multiplie seulement le numérateur. Le dénominateur ne change pas.', ex: '2/3 × 5 = 10/3' },
            { t: 'Soustraire un nombre négatif', p: 3, r: 'Soustraire un nombre négatif revient à ajouter son opposé.', ex: '(-8) - (-5) = -8 + 5 = -3' },
            { t: 'Fractions égales', p: 4, r: 'On multiplie (ou on divise) le numérateur et le dénominateur par le même nombre.', ex: '9/15 = 3/5 = 6/10' },
          ].map((c, i) => (
            <motion.div key={c.t} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.08 }}>
              <Card className="h-full">
                <p className="flex items-center gap-2 font-bold text-foreground"><Lightbulb className="size-5 text-primary" />{c.t}<Page n={c.p} /></p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{c.r}</p>
                <p className="mt-3 rounded-2xl bg-muted/50 px-4 py-3 text-center text-lg font-semibold text-foreground" dir="ltr"><MathText text={c.ex} /></p>
              </Card>
            </motion.div>
          ))}
        </div>
      </Section>
      <Section id="practice" letter="E" title="À toi de jouer" kicker="Pratique"><Practice onDone={mark('practice')} /></Section>
      <Section id="check" letter="F" title="Vérifie ce que tu as compris" kicker="Vérification"><Check4 onDone={(s) => { setScore(s); mark('check')() }} /></Section>
      <Section id="summary" letter="G" title="Les quatre idées clés" kicker="Résumé">
        <Card className="bg-gradient-to-br from-emerald-500/10 via-card to-primary/10">
          <ul className="grid gap-3 md:grid-cols-2">
            {['Une fraction = des parts égales d’un tout.', 'On additionne des fractions de même dénominateur.', 'Fraction × entier : seul le numérateur change.', 'Moins un négatif = plus son opposé.'].map((t) => (
              <li key={t} className="flex items-start gap-2 text-base font-semibold text-foreground"><ChevronRight className="mt-0.5 size-5 shrink-0 text-primary" />{t}</li>
            ))}
          </ul>
          <div className="mt-6 flex flex-wrap items-center gap-4 rounded-2xl bg-background/80 p-4">
            <Award className={cn('size-10', done.size >= 7 ? 'text-primary' : 'text-muted-foreground')} />
            <div>
              <p className="font-bold text-foreground">{done.size >= 7 ? 'Leçon terminée' : 'Activités faites'} : {done.size} / 7</p>
              <p className="text-sm text-muted-foreground">{score !== null ? `Vérification : ${score} / ${QUESTIONS.length} réussies du premier coup.` : 'Termine la vérification (F) pour voir ton score.'}</p>
            </div>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">Contenu tiré des notes de cours de démonstration rédigées par l’équipe TRACE (p. 1 à 4). Les calculs et les corrections sont faits par le code, pas par une IA.</p>
        </Card>
      </Section>
    </div>
  )
}
