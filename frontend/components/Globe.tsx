'use client';

import { useEffect, useRef, useCallback } from 'react';
import createGlobe from 'cobe';

interface Props {
  lat: number;
  lng: number;
  onLocationChange?: (lat: number, lng: number) => void;
}

export default function Globe({ lat, lng, onLocationChange }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerInteracting = useRef<number | null>(null);
  const pointerInteractionMovement = useRef(0);
  const phiRef = useRef(0);
  const thetaRef = useRef(0);
  const focusRef = useRef({ phi: 0, theta: 0 });

  // Convert lat/lng to phi/theta for cobe
  const locationToAngles = useCallback((lat: number, lng: number) => {
    return {
      phi: (90 - lat) * (Math.PI / 180),
      theta: (lng + 180) * (Math.PI / 180),
    };
  }, []);

  useEffect(() => {
    const angles = locationToAngles(lat, lng);
    focusRef.current = angles;
  }, [lat, lng, locationToAngles]);

  useEffect(() => {
    if (!canvasRef.current) return;

    let width = 0;
    const onResize = () => {
      if (canvasRef.current) {
        width = canvasRef.current.offsetWidth;
      }
    };
    onResize();
    window.addEventListener('resize', onResize);

    const angles = locationToAngles(lat, lng);
    phiRef.current = angles.phi;
    thetaRef.current = angles.theta;

    const globe = createGlobe(canvasRef.current, {
      devicePixelRatio: 2,
      width: width * 2,
      height: width * 2,
      phi: angles.phi,
      theta: angles.theta,
      dark: 0,
      diffuse: 1.2,
      mapSamples: 24000,
      mapBrightness: 3.5,
      baseColor: [1, 0.9, 0.8],
      markerColor: [0.4, 0.7, 0.4],
      glowColor: [0.9, 0.85, 0.95],
      markers: [{ location: [lat, lng], size: 0.06 }],
      onRender: (state) => {
        // Smooth rotation toward focus point
        if (!pointerInteracting.current) {
          const target = focusRef.current;
          const distPhi = target.phi - phiRef.current;
          const distTheta = target.theta - thetaRef.current;
          phiRef.current += distPhi * 0.08;
          thetaRef.current += distTheta * 0.08;
        }

        state.phi = phiRef.current;
        state.theta = thetaRef.current;
        state.width = width * 2;
        state.height = width * 2;
      },
    });

    const canvas = canvasRef.current;

    const onPointerDown = (e: PointerEvent) => {
      pointerInteracting.current = e.clientX - pointerInteractionMovement.current;
      canvas.style.cursor = 'grabbing';
    };

    const onPointerUp = () => {
      pointerInteracting.current = null;
      canvas.style.cursor = 'grab';
    };

    const onPointerOut = () => {
      pointerInteracting.current = null;
      canvas.style.cursor = 'grab';
    };

    const onPointerMove = (e: PointerEvent) => {
      if (pointerInteracting.current !== null) {
        const delta = e.clientX - pointerInteracting.current;
        pointerInteractionMovement.current = delta;
        thetaRef.current += delta * 0.005;
        pointerInteracting.current = e.clientX;
      }
    };

    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointerout', onPointerOut);
    canvas.addEventListener('pointermove', onPointerMove);

    return () => {
      globe.destroy();
      window.removeEventListener('resize', onResize);
      canvas.removeEventListener('pointerdown', onPointerDown);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointerout', onPointerOut);
      canvas.removeEventListener('pointermove', onPointerMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="globe-canvas"
      style={{ width: '100%', height: '100%', cursor: 'grab', aspectRatio: '1' }}
    />
  );
}
