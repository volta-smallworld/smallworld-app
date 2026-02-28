'use client';

import { useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import Chat from '@/components/Chat';
import FilterPanel from '@/components/FilterPanel';
import ResultsGallery from '@/components/ResultsGallery';
import { Viewpoint, analyze, exportCSV, AnalyzeRequest } from '@/lib/api';

// Leaflet must be loaded client-side only (no SSR)
const MapView = dynamic(() => import('@/components/MapView'), { ssr: false });

type Tab = 'chat' | 'results' | 'filters';

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('filters');
  const [viewpoints, setViewpoints] = useState<Viewpoint[]>([]);
  const [selectedViewpoint, setSelectedViewpoint] = useState<Viewpoint | null>(null);
  const [searchCenter, setSearchCenter] = useState<{ lat: number; lng: number } | null>(null);
  const [searchRadius, setSearchRadius] = useState(10);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<'ground' | 'drone'>('ground');
  const [featureWeights, setFeatureWeights] = useState<Record<string, number>>({
    peaks: 0.7, ridges: 0.5, cliffs: 0.6, water: 0.6, relief: 0.5,
  });
  const [beautyWeights, setBeautyWeights] = useState<Record<string, number>>({
    viewshed_richness: 0.20, viewpoint_entropy: 0.15, skyline_fractal: 0.20,
    prospect_refuge: 0.15, depth_layering: 0.10, mystery: 0.10, water_visibility: 0.10,
  });

  const handleMapClick = useCallback((lat: number, lng: number) => {
    setSearchCenter({ lat, lng });
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!searchCenter) return;
    setLoading(true);
    try {
      const req: AnalyzeRequest = {
        center_lat: searchCenter.lat,
        center_lng: searchCenter.lng,
        radius_km: searchRadius,
        mode,
        feature_weights: featureWeights,
        beauty_weights: beautyWeights,
        max_results: 20,
        compute_lighting: true,
      };
      const res = await analyze(req);
      setViewpoints(res.viewpoints);
      setActiveTab('results');
    } catch (err) {
      console.error('Analysis failed:', err);
    } finally {
      setLoading(false);
    }
  }, [searchCenter, searchRadius, mode, featureWeights, beautyWeights]);

  const handleChatResults = useCallback((results: Viewpoint[]) => {
    setViewpoints(results);
    if (results.length > 0) {
      setSearchCenter({ lat: results[0].lat, lng: results[0].lng });
    }
  }, []);

  const handleExportCSV = useCallback(async () => {
    try {
      const csv = await exportCSV();
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'smallworld_drone_mission.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    }
  }, []);

  return (
    <div className="app">
      <header className="header">
        <h1>smallworld</h1>
        <span className="tagline">algorithmic photography angle finder</span>
      </header>

      <div className="map-area">
        <MapView
          center={searchCenter}
          radius={searchRadius}
          viewpoints={viewpoints}
          selectedViewpoint={selectedViewpoint}
          onMapClick={handleMapClick}
          onViewpointClick={setSelectedViewpoint}
        />
      </div>

      <div className="sidebar">
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'chat' ? 'active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            Chat
          </button>
          <button
            className={`tab ${activeTab === 'results' ? 'active' : ''}`}
            onClick={() => setActiveTab('results')}
          >
            Results {viewpoints.length > 0 && `(${viewpoints.length})`}
          </button>
          <button
            className={`tab ${activeTab === 'filters' ? 'active' : ''}`}
            onClick={() => setActiveTab('filters')}
          >
            Filters
          </button>
        </div>

        {activeTab === 'chat' && (
          <Chat
            loading={loading}
            setLoading={setLoading}
            onResults={handleChatResults}
          />
        )}

        {activeTab === 'results' && (
          <>
            <ResultsGallery
              viewpoints={viewpoints}
              selectedViewpoint={selectedViewpoint}
              onSelect={setSelectedViewpoint}
            />
            {viewpoints.length > 0 && (
              <div className="export-bar">
                <button className="export-btn" onClick={handleExportCSV}>
                  Export Litchi CSV
                </button>
              </div>
            )}
          </>
        )}

        {activeTab === 'filters' && (
          <FilterPanel
            mode={mode}
            setMode={setMode}
            featureWeights={featureWeights}
            setFeatureWeights={setFeatureWeights}
            beautyWeights={beautyWeights}
            setBeautyWeights={setBeautyWeights}
            searchRadius={searchRadius}
            setSearchRadius={setSearchRadius}
            searchCenter={searchCenter}
            onAnalyze={handleAnalyze}
            loading={loading}
          />
        )}
      </div>
    </div>
  );
}
