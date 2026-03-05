"use client";

import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float } from "@react-three/drei";
import * as THREE from "three";
import { vertexShader, fragmentShader } from "./orb-shaders";

interface OrbMeshProps {
  speed: number;
  colorShift: number;
}

function OrbMesh({ speed, colorShift }: OrbMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSpeed: { value: speed },
      uNoiseAmplitude: { value: 0.15 },
      uColorShift: { value: colorShift },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useFrame((_, delta) => {
    if (!meshRef.current) return;
    const mat = meshRef.current.material as THREE.ShaderMaterial;
    mat.uniforms.uTime.value += delta;
    // Lerp speed and colorShift for smooth transitions
    mat.uniforms.uSpeed.value += (speed - mat.uniforms.uSpeed.value) * 0.05;
    mat.uniforms.uColorShift.value +=
      (colorShift - mat.uniforms.uColorShift.value) * 0.05;
  });

  return (
    <Float speed={1.5} rotationIntensity={0.3} floatIntensity={0.5}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1.5, 64]} />
        <shaderMaterial
          vertexShader={vertexShader}
          fragmentShader={fragmentShader}
          uniforms={uniforms}
        />
      </mesh>
    </Float>
  );
}

interface OrbProps {
  size: number;
  speed: number;
  colorShift: number;
  className?: string;
}

export function Orb({ size, speed, colorShift, className }: OrbProps) {
  return (
    <div className={className} style={{ width: size, height: size }}>
      <Canvas
        gl={{ alpha: true, antialias: true }}
        dpr={[1, 2]}
        camera={{ position: [0, 0, 4], fov: 45 }}
        style={{ background: "transparent" }}
      >
        <OrbMesh speed={speed} colorShift={colorShift} />
      </Canvas>
    </div>
  );
}
