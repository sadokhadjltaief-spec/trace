'use client'

// A geometric solid picked by the engine (fixed list), drawn with Three.js and rotatable. Simple models for
// intuition, not exact scientific renderings.
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { Model3D } from '../textbook/models-3d'

export function Solid3D({ kind, params, label }: { kind: string; params: Record<string, unknown>; label: string }) {
  return (
    <div className="h-72 w-full overflow-hidden rounded-3xl bg-gradient-to-b from-secondary/60 to-card" role="img" aria-label={label}>
      <Canvas dpr={[1, 1.75]} camera={{ position: [2.4, 1.8, 2.6], fov: 40 }}>
        <ambientLight intensity={0.8} />
        <directionalLight position={[3, 5, 2]} intensity={1.1} />
        <Model3D kind={kind} params={params} />
        <OrbitControls enablePan={false} enableZoom={false} autoRotate autoRotateSpeed={1} />
      </Canvas>
    </div>
  )
}
