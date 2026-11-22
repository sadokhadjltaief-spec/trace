'use client'

// A fraction as part of a whole, drawn as a REAL geometric solid: a cylinder cut into `den` equal sectors (each sector
// is a CylinderGeometry slice of angle 2π/den), `num` of them coloured and slightly pulled out. Equal sectors have
// equal volume, so the coloured volume is exactly num/den of the cylinder. Drag to rotate. Three.js is used here
// only because the object is a solid; without WebGL a flat SVG disc shows the same fraction.
import { useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'

const ON = '#ec7418'
const OFF = '#f3ead9'
const EDGE = '#5b4636'

function Slice({ i, den, on, explode }: { i: number; den: number; on: boolean; explode: number }) {
  const angle = (Math.PI * 2) / den
  const geometry = useMemo(() => new THREE.CylinderGeometry(1.25, 1.25, 0.55, Math.max(8, Math.ceil(64 / den)), 1, false, i * angle, angle), [i, den, angle])
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 30), [geometry])
  const mid = i * angle + angle / 2
  // CylinderGeometry's theta starts on +z and turns towards +x
  const offset: [number, number, number] = on ? [Math.sin(mid) * explode, 0, Math.cos(mid) * explode] : [0, 0, 0]
  return (
    <group position={offset}>
      <mesh geometry={geometry}>
        <meshStandardMaterial color={on ? ON : OFF} roughness={0.55} metalness={0.05} />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={EDGE} />
      </lineSegments>
    </group>
  )
}

export function FractionCake3D({ num, den, height = 260, label, reduced = false }: { num: number; den: number; height?: number; label: string; reduced?: boolean }) {
  return (
    <div className="relative w-full overflow-hidden rounded-3xl bg-gradient-to-b from-secondary/60 to-card" style={{ height }} role="img" aria-label={label}>
      <Canvas dpr={[1, 1.75]} camera={{ position: [0, 2.6, 3.4], fov: 40 }}>
        <ambientLight intensity={0.75} />
        <directionalLight position={[3, 5, 2]} intensity={1.1} />
        <directionalLight position={[-3, 2, -2]} intensity={0.35} />
        <group rotation={[0.08, 0, 0]}>
          {Array.from({ length: den }, (_, i) => <Slice key={`${den}-${i}`} i={i} den={den} on={i < num} explode={0.12} />)}
        </group>
        <OrbitControls enablePan={false} enableZoom={false} autoRotate={!reduced} autoRotateSpeed={1.2} minPolarAngle={0.3} maxPolarAngle={1.35} />
      </Canvas>
    </div>
  )
}

// Same fraction as a flat disc (no WebGL, or as a second view).
export function FractionDisc({ num, den, size = 120, label }: { num: number; den: number; size?: number; label: string }) {
  const r = 50
  const parts = Array.from({ length: den }, (_, i) => {
    const a0 = (i / den) * Math.PI * 2 - Math.PI / 2
    const a1 = ((i + 1) / den) * Math.PI * 2 - Math.PI / 2
    const large = a1 - a0 > Math.PI ? 1 : 0
    const d = den === 1
      ? `M 60 10 A 50 50 0 1 1 59.99 10 Z`
      : `M 60 60 L ${60 + r * Math.cos(a0)} ${60 + r * Math.sin(a0)} A ${r} ${r} 0 ${large} 1 ${60 + r * Math.cos(a1)} ${60 + r * Math.sin(a1)} Z`
    return <path key={i} d={d} fill={i < num ? ON : OFF} stroke={EDGE} strokeWidth={1.2} />
  })
  return <svg viewBox="0 0 120 120" width={size} height={size} role="img" aria-label={label}>{parts}</svg>
}

export function webglOk() {
  try {
    const c = document.createElement('canvas')
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')))
  } catch {
    return false
  }
}
