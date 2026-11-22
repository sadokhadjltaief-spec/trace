'use client'

// The open hardcover book on a desk (React Three Fiber + drei). Camera ~58° above the desk, warm directional sun with
// soft shadows, matte textured desk, yellow cloth cover, stacked page thickness, pages curved near the spine, blue
// ribbon bookmark, page-turn animation. The pages' content is real DOM in a layer above the canvas: every frame the 4
// corners of the open spread are projected to the screen and the layer gets the matching perspective (CSS matrix3d),
// so the question, the flap and the vocabulary are ordinary, fully interactive elements lying on the 3D pages.
// (drei <Html> mounts a second React root, which React 19's dev double-mount removed: hence this projection.)
// The 3D model (if any) floats above the right page and turns with the mouse.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { PresentationControls } from '@react-three/drei'
import * as THREE from 'three'
import { LeftPage, RightPage, type BookCopy, type Spread } from './pages'
import { Model3D } from './models-3d'

const PAGE_W = 4
const PAGE_D = 5.4
const LIFT = 0.22 // page height above the page stack, reached ~1.1 units from the spine
const STACK = 0.28
const HTML_PX_W = 420 // DOM size of a page; scaled to the page in world units
const HTML_PX_H = 640
// gap left at the spine between the two pages, in DOM px (2 x 0.55 world units, where the pages curve)
const SPINE_PX = Math.round((1.1 * HTML_PX_W) / (PAGE_W - 0.55))

function canvasTexture(draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void, w = 512, h = 512, repeat = 1) {
  const c = document.createElement('canvas'); c.width = w; c.height = h
  draw(c.getContext('2d')!, w, h)
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat, repeat)
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4
  return t
}

function useTextures() {
  return useMemo(() => {
    const desk = canvasTexture((ctx, w, h) => {
      ctx.fillStyle = '#b59f80'; ctx.fillRect(0, 0, w, h)
      for (let i = 0; i < 14000; i++) { // matte grain
        const v = Math.random() * 30 - 15
        ctx.fillStyle = `rgba(${120 + v},${100 + v},${75 + v},0.10)`; ctx.fillRect(Math.random() * w, Math.random() * h, 2, 2)
      }
      for (let y = 0; y < h; y += 3) { ctx.fillStyle = `rgba(90,70,50,${Math.random() * 0.05})`; ctx.fillRect(0, y, w, 1) }
    }, 512, 512, 6)
    const cloth = canvasTexture((ctx, w, h) => {
      ctx.fillStyle = '#e2ad38'; ctx.fillRect(0, 0, w, h)
      for (let x = 0; x < w; x += 4) { ctx.fillStyle = 'rgba(120,80,10,0.10)'; ctx.fillRect(x, 0, 1, h) }
      for (let y = 0; y < h; y += 4) { ctx.fillStyle = 'rgba(255,240,190,0.10)'; ctx.fillRect(0, y, w, 1) }
    }, 256, 256, 4)
    const paper = canvasTexture((ctx, w, h) => {
      ctx.fillStyle = '#fbf5e6'; ctx.fillRect(0, 0, w, h)
      for (let i = 0; i < 4000; i++) { ctx.fillStyle = `rgba(160,130,90,${Math.random() * 0.05})`; ctx.fillRect(Math.random() * w, Math.random() * h, 1, 1) }
    }, 256, 256, 2)
    const edge = canvasTexture((ctx, w, h) => { // stacked page edges
      ctx.fillStyle = '#efe5cf'; ctx.fillRect(0, 0, w, h)
      for (let y = 0; y < h; y += 2) { ctx.fillStyle = `rgba(120,100,70,${0.08 + Math.random() * 0.1})`; ctx.fillRect(0, y, w, 1) }
    }, 64, 128, 1)
    return { desk, cloth, paper, edge }
  }, [])
}

/** A page lying in the XZ plane, spanning x in [0, PAGE_W] (mirrored for the left page), curved up near the spine. */
function usePageGeometry() {
  return useMemo(() => {
    const g = new THREE.PlaneGeometry(PAGE_W, PAGE_D, 48, 1)
    g.rotateX(-Math.PI / 2)
    g.translate(PAGE_W / 2, 0, 0)
    const pos = g.attributes.position as THREE.BufferAttribute
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i)
      const t = Math.min(x / 1.1, 1)
      pos.setY(i, LIFT * (1 - (1 - t) * (1 - t)) - 0.02 * Math.max(0, x - 3.6))
    }
    g.computeVertexNormals()
    return g
  }, [])
}

function Turner({ dir, onDone, geometry, paper }: { dir: 1 | -1; onDone: () => void; geometry: THREE.BufferGeometry; paper: THREE.Texture }) {
  const ref = useRef<THREE.Group>(null)
  const t0 = useRef<number | null>(null)
  useFrame(({ clock }) => {
    if (!ref.current) return
    if (t0.current === null) t0.current = clock.elapsedTime
    const p = Math.min(1, (clock.elapsedTime - t0.current) / 0.75)
    const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
    // next: the right page lifts on the spine and lands on the left; previous: the reverse
    ref.current.rotation.z = dir === 1 ? e * Math.PI : Math.PI - e * Math.PI
    if (p >= 1) onDone()
  })
  return (
    <group ref={ref} position={[0, STACK + 0.01, 0]}>
      <mesh geometry={geometry} castShadow>
        <meshStandardMaterial map={paper} side={THREE.DoubleSide} roughness={0.95} />
      </mesh>
    </group>
  )
}

export type BookProps = {
  spread: Spread
  index: number
  copy: BookCopy
  turning: 1 | -1 | 0
  onTurned: () => void
  onAnswer: (i: number) => Promise<void>
  onVocab: () => void
  onVisual: () => void
}

/** Keeps the whole open book in view whatever the window shape, seen ~58° above the desk. */
function FitCamera() {
  const { camera, size } = useThree()
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const v = THREE.MathUtils.degToRad(cam.fov)
    const aspect = size.width / Math.max(1, size.height)
    const h = 2 * Math.atan(Math.tan(v / 2) * aspect)
    const d = Math.max(4.9 / Math.tan(h / 2), 3.6 / Math.tan(v / 2)) * 1.02
    const a = THREE.MathUtils.degToRad(58)
    cam.position.set(0, d * Math.sin(a), d * Math.cos(a) + 0.35)
    cam.lookAt(0, 0, 0.35)
    cam.updateProjectionMatrix()
  }, [camera, size.width, size.height])
  return null
}

function Scene({ spread, turning, onTurned, onVisual, overlay, index }: BookProps & { overlay: React.RefObject<HTMLDivElement | null> }) {
  const tex = useTextures()
  const page = usePageGeometry()
  const has3d = spread.model3d?.kind && spread.model3d.kind !== 'none'
  return (
    <>
      <FitCamera />
      <color attach="background" args={['#3a2f26']} />
      <hemisphereLight args={['#fff4e0', '#5a4632', 0.55]} />
      <directionalLight position={[6, 11, 5]} intensity={1.9} color="#ffe8c2" castShadow
        shadow-mapSize={[2048, 2048]} shadow-camera-left={-8} shadow-camera-right={8} shadow-camera-top={8} shadow-camera-bottom={-8} shadow-bias={-0.0004} />
      {/* desk */}
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.06, 0]} receiveShadow>
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial map={tex.desk} roughness={0.95} />
      </mesh>
      {/* cloth hardcover */}
      <mesh position={[0, -0.02, 0]} receiveShadow castShadow>
        <boxGeometry args={[PAGE_W * 2 + 0.35, 0.08, PAGE_D + 0.35]} />
        <meshStandardMaterial map={tex.cloth} roughness={0.85} />
      </mesh>
      {/* stacked pages (visible thickness) */}
      {[-1, 1].map((s) => (
        <mesh key={s} position={[s * (PAGE_W / 2 + 0.03), STACK / 2, 0]} castShadow receiveShadow>
          <boxGeometry args={[PAGE_W - 0.05, STACK, PAGE_D - 0.05]} />
          <meshStandardMaterial attach="material-0" map={tex.edge} />
          <meshStandardMaterial attach="material-1" map={tex.edge} />
          <meshStandardMaterial attach="material-2" color="#fbf5e6" />
          <meshStandardMaterial attach="material-3" color="#e9dfc8" />
          <meshStandardMaterial attach="material-4" map={tex.edge} />
          <meshStandardMaterial attach="material-5" map={tex.edge} />
        </mesh>
      ))}
      {/* the two open pages, curved at the spine */}
      <mesh geometry={page} position={[0.02, STACK, 0]} receiveShadow castShadow>
        <meshStandardMaterial map={tex.paper} roughness={0.95} side={THREE.DoubleSide} />
      </mesh>
      <mesh geometry={page} position={[-0.02, STACK, 0]} scale={[-1, 1, 1]} receiveShadow castShadow>
        <meshStandardMaterial map={tex.paper} roughness={0.95} side={THREE.DoubleSide} />
      </mesh>
      {/* spine shadow line */}
      <mesh position={[0, STACK + 0.002, 0]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[0.12, PAGE_D]} />
        <meshBasicMaterial color="#000" transparent opacity={0.18} />
      </mesh>
      {/* blue ribbon bookmark hanging from the bottom of the spine */}
      <mesh position={[0.15, 0.0, PAGE_D / 2 + 0.55]} rotation={[-Math.PI / 2, 0, 0.12]} receiveShadow castShadow>
        <planeGeometry args={[0.2, 1.3]} />
        <meshStandardMaterial color="#2f5fb3" roughness={0.6} side={THREE.DoubleSide} />
      </mesh>
      {/* page content: real, interactive DOM laid on the pages */}
      <ProjectOverlay target={overlay} hidden={!!turning} />
      {has3d ? (
        <PresentationControls global={false} cursor snap={false} speed={1.6} rotation={[0.35, -0.5, 0]} polar={[-0.6, 0.9]} azimuth={[-Math.PI, Math.PI]}>
          <group position={[2.35, STACK + LIFT + 0.75, 1.25]} scale={0.55} onPointerDown={onVisual}>
            <Model3D kind={spread.model3d.kind} params={spread.model3d.params} />
          </group>
        </PresentationControls>
      ) : null}
      {turning ? <Turner key={`${index}-${turning}`} dir={turning} onDone={onTurned} geometry={page} paper={tex.paper} /> : null}
    </>
  )
}

// ---- homography: CSS matrix3d that maps the DOM rectangle (0,0)-(w,h) onto 4 projected screen points
type M3 = number[]
const adj = (m: M3): M3 => [
  m[4] * m[8] - m[5] * m[7], m[2] * m[7] - m[1] * m[8], m[1] * m[5] - m[2] * m[4],
  m[5] * m[6] - m[3] * m[8], m[0] * m[8] - m[2] * m[6], m[2] * m[3] - m[0] * m[5],
  m[3] * m[7] - m[4] * m[6], m[1] * m[6] - m[0] * m[7], m[0] * m[4] - m[1] * m[3],
]
const mulMM = (a: M3, b: M3): M3 => {
  const c: M3 = []
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) { let x = 0; for (let k = 0; k < 3; k++) x += a[3 * i + k] * b[3 * k + j]; c[3 * i + j] = x }
  return c
}
const mulMV = (m: M3, v: number[]) => [m[0] * v[0] + m[1] * v[1] + m[2] * v[2], m[3] * v[0] + m[4] * v[1] + m[5] * v[2], m[6] * v[0] + m[7] * v[1] + m[8] * v[2]]
const basis = (p: number[]): M3 => {
  const m = [p[0], p[2], p[4], p[1], p[3], p[5], 1, 1, 1]
  const v = mulMV(adj(m), [p[6], p[7], 1])
  return mulMM(m, [v[0], 0, 0, 0, v[1], 0, 0, 0, v[2]])
}
function matrix3d(w: number, h: number, dst: number[]) {
  const t = mulMM(basis(dst), adj(basis([0, 0, w, 0, 0, h, w, h])))
  const n = t.map((x) => x / t[8])
  return `matrix3d(${n[0]},${n[3]},0,${n[6]},${n[1]},${n[4]},0,${n[7]},0,0,1,0,${n[2]},${n[5]},0,${n[8]})`
}

const SPREAD_PX_W = HTML_PX_W * 2 + SPINE_PX
const HALF_W = PAGE_W   // world half-width covered by the DOM spread (pages from 0.55 to 4.0 each side + spine)
const HALF_D = ((HTML_PX_H * (PAGE_W - 0.55)) / HTML_PX_W) / 2

function ProjectOverlay({ target, hidden }: { target: React.RefObject<HTMLDivElement | null>; hidden: boolean }) {
  const { camera, size } = useThree()
  const v = useMemo(() => new THREE.Vector3(), [])
  const last = useRef('')
  useFrame(() => {
    const el = target.current
    if (!el) return
    const y = STACK + LIFT + 0.002
    const pts: number[] = []
    for (const [x, z] of [[-HALF_W, -HALF_D], [HALF_W, -HALF_D], [-HALF_W, HALF_D], [HALF_W, HALF_D]]) {
      v.set(x, y, z).project(camera)
      pts.push(((v.x + 1) / 2) * size.width, ((1 - v.y) / 2) * size.height)
    }
    const m = matrix3d(SPREAD_PX_W, HTML_PX_H, pts)
    if (m !== last.current) { el.style.transform = m; last.current = m }
    el.style.opacity = hidden ? '0' : '1'
  })
  return null
}

export function Book3D(props: BookProps) {
  const [ready, setReady] = useState(false)
  const overlay = useRef<HTMLDivElement>(null)
  useEffect(() => setReady(true), [])
  if (!ready) return null
  const { spread, index, copy, onAnswer, onVocab, onVisual } = props
  const has3d = !!spread.model3d?.kind && spread.model3d.kind !== 'none'
  return (
    <div className="relative h-full w-full overflow-hidden">
      <Canvas shadows dpr={[1, 1.75]} camera={{ position: [0, 8.6, 5.6], fov: 42 }} onCreated={({ camera }) => camera.lookAt(0, 0, 0.35)}
        gl={{ antialias: true, powerPreference: 'high-performance' }}>
        <Scene {...props} overlay={overlay} />
      </Canvas>
      {/* the pages' DOM, laid on the 3D spread by ProjectOverlay (pointer events only on the page content) */}
      <div ref={overlay} className="pointer-events-none absolute start-0 top-0 transition-opacity duration-200"
        style={{ width: SPREAD_PX_W, height: HTML_PX_H, transformOrigin: '0 0', opacity: 0 }} dir="ltr">
        <div key={`s${index}`} className="flex h-full select-none">
          <div className="pointer-events-auto" style={{ width: HTML_PX_W, height: HTML_PX_H, padding: '18px 20px 14px 16px' }}>
            <LeftPage spread={spread} copy={copy} number={index + 1} onAnswer={onAnswer} onVocab={onVocab} />
          </div>
          <div style={{ width: SPINE_PX }} />
          <div className="pointer-events-auto" style={{ width: HTML_PX_W, height: HTML_PX_H, padding: '18px 16px 14px 20px' }}>
            <RightPage spread={spread} copy={copy} onVisual={onVisual} has3d={has3d} />
          </div>
        </div>
      </div>
    </div>
  )
}

export function webglAvailable() {
  try {
    const c = document.createElement('canvas')
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')))
  } catch {
    return false
  }
}
