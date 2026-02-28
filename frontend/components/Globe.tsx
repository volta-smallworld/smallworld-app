'use client';

import { useEffect, useRef } from 'react';

interface Props {
  lat: number;
  lng: number;
  onLocationChange?: (lat: number, lng: number) => void;
}

export default function Globe({ lat, lng, onLocationChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const globeRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let destroyed = false;

    // Dynamic import to avoid SSR issues with Three.js
    import('globe.gl').then((GlobeModule) => {
      if (destroyed || !containerRef.current) return;

      const Globe = GlobeModule.default;
      const globe = new (Globe as any)()
        .globeImageUrl('//unpkg.com/three-globe/example/img/earth-blue-marble.jpg')
        .bumpImageUrl('//unpkg.com/three-globe/example/img/earth-topology.png')
        .backgroundImageUrl('//unpkg.com/three-globe/example/img/night-sky.png')
        .showAtmosphere(true)
        .atmosphereColor('#b0c4de')
        .atmosphereAltitude(0.2)
        .pointOfView({ lat, lng, altitude: 2.0 }, 0)
        .pointsData([{ lat, lng, size: 0.6, color: '#34c759' }])
        .pointAltitude('size')
        .pointColor('color')
        .pointRadius(0.4)
        .width(containerRef.current.clientWidth)
        .height(containerRef.current.clientHeight)
        (containerRef.current);

      // Click handler: convert screen click to lat/lng
      globe.onGlobeClick(({ lat: clickLat, lng: clickLng }: { lat: number; lng: number }) => {
        if (onLocationChange) {
          onLocationChange(clickLat, clickLng);
        }
      });

      globeRef.current = globe;

      // Handle resize
      const onResize = () => {
        if (containerRef.current && globeRef.current) {
          globeRef.current
            .width(containerRef.current.clientWidth)
            .height(containerRef.current.clientHeight);
        }
      };
      window.addEventListener('resize', onResize);

      return () => {
        window.removeEventListener('resize', onResize);
      };
    });

    return () => {
      destroyed = true;
      if (globeRef.current && globeRef.current._destructor) {
        globeRef.current._destructor();
      }
      // Clean up the Three.js canvas
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, []);

  // Update marker and camera when location changes
  useEffect(() => {
    if (!globeRef.current) return;
    globeRef.current
      .pointsData([{ lat, lng, size: 0.6, color: '#34c759' }])
      .pointOfView({ lat, lng, altitude: 2.0 }, 1000);
  }, [lat, lng]);

  return (
    <div
      ref={containerRef}
      className="globe-3d"
      style={{ width: '100%', height: '100%' }}
    />
  );
}
