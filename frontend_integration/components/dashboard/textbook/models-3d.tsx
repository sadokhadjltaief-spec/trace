'use client'

// The few 3D models a spread may show (fixed list, chosen by the engine; parameters clamped here). Drawn "ink on
// paper": a light fill + dark edge lines. These are simple models for intuition, not exact scientific renderings.
import { useMemo } from 'react'
import * as THREE from 'three'

const INK = '#2b2520'
const FILL = '#f6e7c8'
const num = (v: unknown, d: number, lo = 0.2, hi = 3) => {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : d
}

function Inked({ geometry }: { geometry: THREE.BufferGeometry }) {
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 25), [geometry])
  return (
    <group>
      <mesh geometry={geometry} castShadow>
        <meshStandardMaterial color={FILL} roughness={0.9} transparent opacity={0.85} />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={INK} />
      </lineSegments>
    </group>
  )
}

function Arrow({ to, color }: { to: [number, number, number]; color: string }) {
  const dir = new THREE.Vector3(...to)
  const len = Math.max(0.05, dir.length())
  const helper = useMemo(() => new THREE.ArrowHelper(dir.clone().normalize(), new THREE.Vector3(0, 0, 0), len, color, 0.18, 0.1),
    [to[0], to[1], to[2], color]) // eslint-disable-line react-hooks/exhaustive-deps
  return <primitive object={helper} />
}

export function Model3D({ kind, params }: { kind: string; params: Record<string, unknown> }) {
  const geo = useMemo(() => {
    const w = num(params.width, 1.2), h = num(params.height, 1), d = num(params.depth, 0.8), r = num(params.radius, 0.6)
    switch (kind) {
      case 'box': return new THREE.BoxGeometry(w, h, d)
      case 'cylinder': return new THREE.CylinderGeometry(r, r, h, 40)
      case 'cone': return new THREE.ConeGeometry(r, h, 40)
      case 'sphere': return new THREE.SphereGeometry(r, 28, 18)
      case 'pyramid': return new THREE.ConeGeometry(r * 1.2, h, 4)
      case 'prism': {
        const s = new THREE.Shape(); s.moveTo(0, 0); s.lineTo(w, 0); s.lineTo(0, h * 0.8); s.closePath()
        const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false }); g.center(); return g
      }
      case 'wave': {
        const a = num(params.amplitude, 0.4, 0.05, 1), l = num(params.wavelength, 1, 0.3, 3)
        const pts = Array.from({ length: 120 }, (_, i) => { const x = -1.6 + (3.2 * i) / 119; return new THREE.Vector3(x, a * Math.sin((2 * Math.PI * x) / l), 0) })
        return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 200, 0.035, 8, false)
      }
      case 'curve': {
        // points of y = f(x) computed by the engine with SymPy (params.points); nothing is evaluated in the browser
        const raw = (Array.isArray(params.points) ? params.points : []).filter((p): p is number[] => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite))
        if (raw.length < 2) return null
        const xs = raw.map(([x]) => x), ys = raw.map(([, y]) => y)
        const lo = Math.min(...xs), hi = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys)
        const sx = 3 / Math.max(1e-6, hi - lo), sy = 2 / Math.max(1e-6, ymax - ymin)
        const pts = raw.map(([x, y]) => new THREE.Vector3((x - lo) * sx - 1.5, (y - ymin) * sy - 1, 0))
        return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 240, 0.04, 8, false)
      }
      default: return null
    }
  }, [kind, JSON.stringify(params)]) // eslint-disable-line react-hooks/exhaustive-deps

  if (kind === 'vectors') {
    const vs = (Array.isArray(params.vectors) ? params.vectors : [[1, 0, 0], [0, 1, 0]]).slice(0, 3) as number[][]
    const colors = ['#c2410c', '#1d4ed8', '#15803d']
    return (
      <group>
        <axesHelper args={[1.4]} />
        {vs.map((v, i) => <Arrow key={i} to={[num(v[0], 0, -2, 2), num(v[1], 0, -2, 2), num(v[2], 0, -2, 2)]} color={colors[i]} />)}
      </group>
    )
  }
  if (!geo) return null
  return <Inked geometry={geo} />
}
