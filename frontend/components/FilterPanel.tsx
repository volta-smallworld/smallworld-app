'use client';

interface Props {
  mode: 'ground' | 'drone';
  setMode: (mode: 'ground' | 'drone') => void;
  featureWeights: Record<string, number>;
  setFeatureWeights: (w: Record<string, number>) => void;
  beautyWeights: Record<string, number>;
  setBeautyWeights: (w: Record<string, number>) => void;
  searchRadius: number;
  setSearchRadius: (r: number) => void;
  searchCenter: { lat: number; lng: number } | null;
  onAnalyze: () => void;
  loading: boolean;
}

const FEATURE_LABELS: Record<string, string> = {
  peaks: 'Peaks',
  ridges: 'Ridgelines',
  cliffs: 'Cliffs',
  water: 'Water',
  relief: 'Relief',
};

const BEAUTY_LABELS: Record<string, string> = {
  viewshed_richness: 'Viewshed Richness',
  viewpoint_entropy: 'Terrain Diversity',
  skyline_fractal: 'Skyline Complexity',
  prospect_refuge: 'Prospect-Refuge',
  depth_layering: 'Depth Layering',
  mystery: 'Mystery',
  water_visibility: 'Water Visibility',
};

export default function FilterPanel({
  mode, setMode,
  featureWeights, setFeatureWeights,
  beautyWeights, setBeautyWeights,
  searchRadius, setSearchRadius,
  searchCenter, onAnalyze, loading,
}: Props) {
  const updateFeature = (key: string, value: number) => {
    setFeatureWeights({ ...featureWeights, [key]: value });
  };

  const updateBeauty = (key: string, value: number) => {
    setBeautyWeights({ ...beautyWeights, [key]: value });
  };

  return (
    <div className="filters-panel">
      {searchCenter ? (
        <div style={{ marginBottom: '1rem', fontSize: '0.85rem', color: 'var(--clay)' }}>
          Search center: {searchCenter.lat.toFixed(4)}N, {searchCenter.lng.toFixed(4)}
          {searchCenter.lng < 0 ? 'W' : 'E'}
        </div>
      ) : (
        <div style={{ marginBottom: '1rem', fontSize: '0.85rem', color: 'var(--clay)', fontStyle: 'italic' }}>
          Click the map to set a search center
        </div>
      )}

      <div className="filter-group">
        <h4>Mode</h4>
        <div className="mode-toggle">
          <button
            className={`mode-btn ${mode === 'ground' ? 'active' : ''}`}
            onClick={() => setMode('ground')}
          >
            Ground (1.7m)
          </button>
          <button
            className={`mode-btn ${mode === 'drone' ? 'active' : ''}`}
            onClick={() => setMode('drone')}
          >
            Drone (100m)
          </button>
        </div>
      </div>

      <div className="filter-group">
        <h4>Search Radius</h4>
        <div className="filter-slider">
          <label>Radius</label>
          <input
            type="range"
            min={1}
            max={50}
            value={searchRadius}
            onChange={(e) => setSearchRadius(Number(e.target.value))}
          />
          <span className="value">{searchRadius}km</span>
        </div>
      </div>

      <div className="filter-group">
        <h4>Feature Weights</h4>
        {Object.entries(FEATURE_LABELS).map(([key, label]) => (
          <div key={key} className="filter-slider">
            <label>{label}</label>
            <input
              type="range"
              min={0}
              max={100}
              value={(featureWeights[key] || 0) * 100}
              onChange={(e) => updateFeature(key, Number(e.target.value) / 100)}
            />
            <span className="value">{((featureWeights[key] || 0) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>

      <div className="filter-group">
        <h4>Beauty Weights</h4>
        {Object.entries(BEAUTY_LABELS).map(([key, label]) => (
          <div key={key} className="filter-slider">
            <label>{label}</label>
            <input
              type="range"
              min={0}
              max={100}
              value={(beautyWeights[key] || 0) * 100}
              onChange={(e) => updateBeauty(key, Number(e.target.value) / 100)}
            />
            <span className="value">{((beautyWeights[key] || 0) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>

      <button
        className="analyze-btn"
        onClick={onAnalyze}
        disabled={!searchCenter || loading}
      >
        {loading ? 'Analyzing terrain...' : 'Analyze'}
      </button>
    </div>
  );
}
