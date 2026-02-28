'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { Viewpoint } from '@/lib/api';

interface Props {
  center: { lat: number; lng: number } | null;
  radius: number;
  viewpoints: Viewpoint[];
  selectedViewpoint: Viewpoint | null;
  onMapClick: (lat: number, lng: number) => void;
  onViewpointClick: (vp: Viewpoint) => void;
}

export default function MapView({
  center, radius, viewpoints, selectedViewpoint, onMapClick, onViewpointClick,
}: Props) {
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);
  const circleRef = useRef<L.Circle | null>(null);
  const centerMarkerRef = useRef<L.Marker | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Initialize map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [40, -100],
      zoom: 4,
      zoomControl: true,
    });

    // Terrain-focused tile layer (OpenTopoMap)
    L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenTopoMap contributors',
      maxZoom: 17,
    }).addTo(map);

    // Satellite layer as alternative
    const satellite = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: '&copy; Esri', maxZoom: 18 }
    );

    // Layer control
    L.control.layers(
      { 'Terrain': L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png').addTo(map), 'Satellite': satellite },
      {},
      { position: 'topright' }
    ).addTo(map);

    map.on('click', (e: L.LeafletMouseEvent) => {
      onMapClick(e.latlng.lat, e.latlng.lng);
    });

    markersRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // Update search center
  useEffect(() => {
    if (!mapRef.current || !center) return;

    // Remove old center marker and circle
    if (centerMarkerRef.current) centerMarkerRef.current.remove();
    if (circleRef.current) circleRef.current.remove();

    // Add center marker
    const icon = L.divIcon({
      className: 'search-marker',
      iconSize: [10, 10],
      iconAnchor: [5, 5],
    });
    centerMarkerRef.current = L.marker([center.lat, center.lng], { icon })
      .addTo(mapRef.current)
      .bindPopup(`Search center: ${center.lat.toFixed(4)}, ${center.lng.toFixed(4)}`);

    // Add radius circle
    circleRef.current = L.circle([center.lat, center.lng], {
      radius: radius * 1000,
      color: '#5a6e52',
      fillColor: '#5a6e52',
      fillOpacity: 0.08,
      weight: 1,
      dashArray: '4 6',
    }).addTo(mapRef.current);

    // Zoom to fit
    mapRef.current.fitBounds(circleRef.current.getBounds(), { padding: [20, 20] });
  }, [center, radius]);

  // Update viewpoint markers
  useEffect(() => {
    if (!mapRef.current || !markersRef.current) return;

    markersRef.current.clearLayers();

    viewpoints.forEach((vp) => {
      const isSelected = selectedViewpoint?.rank === vp.rank;
      const icon = L.divIcon({
        className: `viewpoint-marker ${isSelected ? 'selected' : ''}`,
        iconSize: isSelected ? [16, 16] : [12, 12],
        iconAnchor: isSelected ? [8, 8] : [6, 6],
      });

      const marker = L.marker([vp.lat, vp.lng], { icon })
        .bindPopup(
          `<b>#${vp.rank}</b> — ${vp.composition}<br>` +
          `Score: ${vp.beauty_total.toFixed(3)}<br>` +
          `${vp.lat.toFixed(4)}N, ${vp.lng.toFixed(4)}W<br>` +
          `Alt: ${vp.altitude_m.toFixed(0)}m, Heading: ${vp.heading_deg.toFixed(0)}°` +
          (vp.lighting ? `<br>Best light: ${vp.lighting.best_time}` : '')
        )
        .on('click', () => onViewpointClick(vp));

      markersRef.current!.addLayer(marker);

      // Draw FOV cone for selected viewpoint
      if (isSelected) {
        const headingRad = (vp.heading_deg * Math.PI) / 180;
        const fovHalf = ((vp.fov_deg / 2) * Math.PI) / 180;
        const coneLen = 0.005; // ~500m in degrees

        const left = [
          vp.lat + Math.cos(headingRad - fovHalf) * coneLen,
          vp.lng + Math.sin(headingRad - fovHalf) * coneLen,
        ] as [number, number];
        const right = [
          vp.lat + Math.cos(headingRad + fovHalf) * coneLen,
          vp.lng + Math.sin(headingRad + fovHalf) * coneLen,
        ] as [number, number];

        L.polygon(
          [[vp.lat, vp.lng], left, right],
          { color: '#c4a882', fillColor: '#c4a882', fillOpacity: 0.15, weight: 1 }
        ).addTo(markersRef.current!);
      }
    });
  }, [viewpoints, selectedViewpoint, onViewpointClick]);

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
    />
  );
}
