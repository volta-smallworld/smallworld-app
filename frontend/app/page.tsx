'use client';

import { useState, useCallback, useRef } from 'react';
import dynamic from 'next/dynamic';
import ResultsGallery from '@/components/ResultsGallery';
import { Viewpoint, analyze, exportCSV, AnalyzeRequest } from '@/lib/api';

const Globe = dynamic(() => import('@/components/Globe'), { ssr: false });
const MapView = dynamic(() => import('@/components/MapView'), { ssr: false });

type View = 'home' | 'results';

// Random scenic locations around the world
const RANDOM_LOCATIONS = [
  { lat: 47.5546, lng: 13.6493, name: 'Hallstatt, Austria' },
  { lat: 64.1466, lng: -21.9426, name: 'Reykjavik, Iceland' },
  { lat: -43.5321, lng: 172.6362, name: 'Christchurch, New Zealand' },
  { lat: 36.2468, lng: -112.1564, name: 'Grand Canyon, USA' },
  { lat: 27.9881, lng: 86.9250, name: 'Everest Region, Nepal' },
  { lat: -22.9519, lng: -43.2105, name: 'Rio de Janeiro, Brazil' },
  { lat: 57.4777, lng: -5.5100, name: 'Scottish Highlands, UK' },
  { lat: 44.4268, lng: -110.5885, name: 'Yellowstone, USA' },
  { lat: -33.8568, lng: 151.2153, name: 'Sydney, Australia' },
  { lat: 62.0397, lng: 6.7560, name: 'Geirangerfjord, Norway' },
  { lat: 45.5152, lng: -122.6784, name: 'Portland, OR, USA' },
  { lat: 46.8182, lng: 8.2275, name: 'Swiss Alps' },
];

export default function Home() {
  const [view, setView] = useState<View>('home');
  const [viewpoints, setViewpoints] = useState<Viewpoint[]>([]);
  const [selectedViewpoint, setSelectedViewpoint] = useState<Viewpoint | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchCenter, setSearchCenter] = useState<{ lat: number; lng: number }>({ lat: 45.5152, lng: -122.6784 });
  const [locationName, setLocationName] = useState('Portland, OR, USA');
  const [searchRadius, setSearchRadius] = useState(10);
  const [mode, setMode] = useState<'ground' | 'drone'>('ground');
  const [loading, setLoading] = useState(false);
  const [manMade, setManMade] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;
    try {
      // Use Nominatim geocoding (free, no API key)
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}&limit=1`
      );
      const data = await res.json();
      if (data.length > 0) {
        const { lat, lon, display_name } = data[0];
        setSearchCenter({ lat: parseFloat(lat), lng: parseFloat(lon) });
        setLocationName(display_name.split(',').slice(0, 3).join(','));
      }
    } catch (err) {
      console.error('Geocoding failed:', err);
    }
  }, [searchQuery]);

  const handleRandomLocation = useCallback(() => {
    const loc = RANDOM_LOCATIONS[Math.floor(Math.random() * RANDOM_LOCATIONS.length)];
    setSearchCenter({ lat: loc.lat, lng: loc.lng });
    setLocationName(loc.name);
    setSearchQuery('');
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
        max_results: 20,
        compute_lighting: true,
      };
      const res = await analyze(req);
      setViewpoints(res.viewpoints);
      setView('results');
    } catch (err) {
      console.error('Analysis failed:', err);
    } finally {
      setLoading(false);
    }
  }, [searchCenter, searchRadius, mode]);

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

  const formatCoord = (lat: number, lng: number) => {
    const latDir = lat >= 0 ? 'N' : 'S';
    const lngDir = lng >= 0 ? 'E' : 'W';
    return `${Math.abs(lat).toFixed(4)}° ${latDir}, ${Math.abs(lng).toFixed(4)}° ${lngDir}`;
  };

  if (view === 'results') {
    return (
      <div className="app results-view">
        <header className="header">
          <div className="header-left">
            <span className="header-brand">by Volta Research</span>
          </div>
          <div className="header-center">
            <h1 className="header-title" onClick={() => setView('home')}>small world</h1>
          </div>
          <div className="header-right">
            <button className="btn-back" onClick={() => setView('home')}>New Search</button>
          </div>
        </header>

        <div className="results-layout">
          <div className="results-map">
            <MapView
              center={searchCenter}
              radius={searchRadius}
              viewpoints={viewpoints}
              selectedViewpoint={selectedViewpoint}
              onMapClick={(lat, lng) => setSearchCenter({ lat, lng })}
              onViewpointClick={setSelectedViewpoint}
            />
          </div>
          <div className="results-sidebar">
            <div className="results-header-bar">
              <span className="results-count">{viewpoints.length} viewpoints found</span>
              {viewpoints.length > 0 && (
                <button className="btn-export" onClick={handleExportCSV}>Export CSV</button>
              )}
            </div>
            <ResultsGallery
              viewpoints={viewpoints}
              selectedViewpoint={selectedViewpoint}
              onSelect={setSelectedViewpoint}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app home-view">
      <header className="header">
        <div className="header-left">
          <span className="header-brand">by Volta Research</span>
        </div>
        <div className="header-right">
          <button className="btn-create-account">Create an account</button>
          <div className="avatar-icon">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
              <circle cx="12" cy="8" r="4" />
              <path d="M12 14c-6 0-8 3-8 5v1h16v-1c0-2-2-5-8-5z" />
            </svg>
          </div>
        </div>
      </header>

      <main className="home-main">
        <div className="home-globe-section">
          <div className="globe-title">
            <h1>small world</h1>
            <span className="coords">[ {formatCoord(searchCenter.lat, searchCenter.lng)} ]</span>
            <span className="location-name">{locationName}</span>
          </div>
          <div className="globe-container">
            <Globe
              lat={searchCenter.lat}
              lng={searchCenter.lng}
              onLocationChange={(lat, lng) => {
                setSearchCenter({ lat, lng });
                setLocationName(`${lat.toFixed(4)}, ${lng.toFixed(4)}`);
              }}
            />
          </div>
        </div>

        <div className="home-controls-section">
          <div className="search-bar">
            <svg className="search-icon" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={searchInputRef}
              type="text"
              placeholder="search the globe"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
          </div>

          <div className="controls-row">
            <button
              className="btn-criteria"
              onClick={handleAnalyze}
              disabled={loading}
            >
              {loading ? 'Analyzing...' : 'Find viewpoints'}
            </button>
            <div className="toggle-group">
              <span className="toggle-label">
                {mode === 'ground' ? 'Ground' : 'Drone'}
              </span>
              <button
                className={`toggle-switch ${mode === 'drone' ? 'active' : ''}`}
                onClick={() => setMode(mode === 'ground' ? 'drone' : 'ground')}
              >
                <span className="toggle-knob" />
              </button>
            </div>
          </div>

          <div className="controls-row">
            <span className="range-label">Range</span>
            <span className="range-unit">km</span>
            <input
              type="range"
              className="range-slider"
              min="1"
              max="50"
              value={searchRadius}
              onChange={(e) => setSearchRadius(parseInt(e.target.value))}
            />
            <span className="range-value">{searchRadius}</span>
          </div>

          <button className="btn-random" onClick={handleRandomLocation}>
            <span>Random location</span>
            <span className="dice">&#127922;</span>
          </button>
        </div>
      </main>

      <footer className="footer">
        <span>Small World, the global adventure assistant</span>
        <span>Powered by Volta Research</span>
      </footer>
    </div>
  );
}
