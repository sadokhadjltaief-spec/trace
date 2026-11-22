'use client'

// SVG diagrams of the lesson. Sizes are proportional to the values (a bar of length 1 = one whole), so what the
// student sees is the mathematics, not a decoration.
import { motion } from 'motion/react'

const ON = 'var(--color-primary, #ec7418)'

// num/den as a bar; num > den draws several wholes side by side. `cut` = extra grid (e.g. a common denominator).
export function FractionBar({ num, den, color = ON, label, wholes, height = 34 }: { num: number; den: number; color?: string; label: string; wholes?: number; height?: number }) {
  const W = Math.max(1, wholes ?? Math.ceil(Math.max(num, 1) / den))
  const unit = 300
  const width = unit * W + (W - 1) * 10
  const cell = unit / den
  const rects = []
  for (let w = 0; w < W; w++) {
    for (let i = 0; i < den; i++) {
      const k = w * den + i
      rects.push(
        <motion.rect key={`${w}-${i}`} x={w * (unit + 10) + i * cell} y={0} width={cell} height={height} rx={2}
          initial={false} animate={{ fill: k < num ? color : 'var(--color-muted, #eee)' }} transition={{ duration: 0.35, delay: k < num ? k * 0.03 : 0 }}
          stroke="var(--color-foreground, #333)" strokeOpacity={0.35} strokeWidth={1} />,
      )
    }
    rects.push(<rect key={`o${w}`} x={w * (unit + 10)} y={0} width={unit} height={height} rx={4} fill="none" stroke="var(--color-foreground, #333)" strokeWidth={1.6} />)
  }
  return (
    <svg viewBox={`-2 -2 ${width + 4} ${height + 4}`} className="w-full" style={{ maxWidth: W * 320 }} role="img" aria-label={label}>
      {rects}
    </svg>
  )
}

// Number line from -12 to 12 with an animated jump from `from` to `to`.
export function NumberLine({ from, to, show, label }: { from: number; to: number | null; show: boolean; label: string }) {
  const lo = -12, hi = 12, W = 640, pad = 20
  const x = (v: number) => pad + ((v - lo) / (hi - lo)) * (W - 2 * pad)
  const ticks = []
  for (let v = lo; v <= hi; v++) {
    ticks.push(
      <g key={v}>
        <line x1={x(v)} x2={x(v)} y1={56} y2={v % 5 === 0 ? 70 : 65} stroke="currentColor" strokeOpacity={0.6} />
        {v % 2 === 0 ? <text x={x(v)} y={86} textAnchor="middle" fontSize={12} fill="currentColor" opacity={v === 0 ? 1 : 0.7} fontWeight={v === 0 ? 700 : 400}>{v}</text> : null}
      </g>,
    )
  }
  const end = to ?? from
  const right = end >= from
  return (
    <svg viewBox={`0 0 ${W} 100`} className="w-full text-foreground" role="img" aria-label={label} style={{ direction: 'ltr' }}>
      <line x1={pad} x2={W - pad} y1={60} y2={60} stroke="currentColor" strokeWidth={2} />
      {ticks}
      <circle cx={x(from)} cy={60} r={7} fill="var(--color-brand-cyan, #3a9ad9)" />
      <text x={x(from)} y={42} textAnchor="middle" fontSize={12} fontWeight={700} fill="var(--color-brand-cyan, #3a9ad9)">départ</text>
      {show && to !== null ? (
        <>
          <motion.path key={`${from}-${to}`} d={`M ${x(from)} 52 Q ${(x(from) + x(end)) / 2} ${8} ${x(end)} 52`} fill="none" stroke={right ? '#10b981' : '#f43f5e'} strokeWidth={3}
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, ease: 'easeInOut' }} markerEnd="url(#arrow)" />
          <motion.circle key={`c${from}-${to}`} cx={x(end)} cy={60} r={8} fill={ON} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.85 }} />
        </>
      ) : null}
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
        </marker>
      </defs>
    </svg>
  )
}
