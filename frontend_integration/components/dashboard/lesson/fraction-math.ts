// Exact fraction arithmetic for the interactive lesson (integers only, no floating point). Every result and every
// answer key in the lesson is computed here, never written by hand or by a model.
export type Frac = { n: number; d: number }

export const gcd = (a: number, b: number): number => (b === 0 ? Math.abs(a) : gcd(b, a % b))
export const lcm = (a: number, b: number) => Math.abs(a * b) / gcd(a, b)

export function simplify(f: Frac): Frac {
  const g = gcd(f.n, f.d) || 1
  const s = f.d < 0 ? -1 : 1
  return { n: (s * f.n) / g, d: (s * f.d) / g }
}
export const add = (a: Frac, b: Frac): Frac => simplify({ n: a.n * b.d + b.n * a.d, d: a.d * b.d })
export const mulInt = (a: Frac, k: number): Frac => simplify({ n: a.n * k, d: a.d })
export const equal = (a: Frac, b: Frac) => a.n * b.d === b.n * a.d
export const less = (a: Frac, b: Frac) => a.n * b.d < b.n * a.d

// "3/5", "-8", "−3", "6/6" -> Frac (null if it is not a plain fraction or integer)
export function parse(s: string): Frac | null {
  const t = s.replace(/−/g, '-').replace(/\s+/g, '')
  const m = t.match(/^(-?\d+)(?:\/(\d+))?$/)
  if (!m) return null
  const d = m[2] ? Number(m[2]) : 1
  return d === 0 ? null : { n: Number(m[1]), d }
}

export const fmt = (f: Frac) => (f.d === 1 ? `${f.n}` : `${f.n}/${f.d}`)

// 10/3 -> "3 + 1/3"
export function mixed(f: Frac): string {
  const s = simplify(f)
  if (s.d === 1 || Math.abs(s.n) < s.d) return fmt(s)
  const q = Math.trunc(s.n / s.d)
  const r = Math.abs(s.n % s.d)
  return r ? `${q} + ${r}/${s.d}` : `${q}`
}
