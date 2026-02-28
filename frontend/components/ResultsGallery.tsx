'use client';

import { Viewpoint } from '@/lib/api';

const BACKEND_URL = 'http://localhost:8000';

interface Props {
  viewpoints: Viewpoint[];
  selectedViewpoint: Viewpoint | null;
  onSelect: (vp: Viewpoint) => void;
}

const SCORE_LABELS: Record<string, string> = {
  viewshed_richness: 'Viewshed',
  viewpoint_entropy: 'Entropy',
  skyline_fractal: 'Fractal',
  prospect_refuge: 'Prospect',
  depth_layering: 'Depth',
  mystery: 'Mystery',
  water_visibility: 'Water',
};

const COMPOSITION_LABELS: Record<string, string> = {
  thirds_upper_right: 'Rule of Thirds (upper right)',
  thirds_upper_left: 'Rule of Thirds (upper left)',
  thirds_lower_right: 'Rule of Thirds (lower right)',
  thirds_lower_left: 'Rule of Thirds (lower left)',
  thirds_diagonal: 'Rule of Thirds (diagonal)',
  golden_upper_right: 'Golden Ratio (upper right)',
  golden_lower_left: 'Golden Ratio (lower left)',
  golden_diagonal: 'Golden Ratio (diagonal)',
  centered: 'Centered',
  symmetry: 'Symmetry',
  leading_line_center: 'Leading Line',
  big_sky: 'Big Sky',
  foreground_emphasis: 'Foreground Emphasis',
  fractal_optimal: 'Fractal Optimal Distance',
};

export default function ResultsGallery({ viewpoints, selectedViewpoint, onSelect }: Props) {
  if (viewpoints.length === 0) {
    return (
      <div className="empty-state">
        <p>
          No results yet. Click the map to set a search area, then use the
          Filters tab to analyze — or ask the chat for recommendations.
        </p>
      </div>
    );
  }

  return (
    <div className="results-panel">
      {viewpoints.map((vp) => (
        <div
          key={vp.rank}
          className={`result-card ${selectedViewpoint?.rank === vp.rank ? 'selected' : ''}`}
          onClick={() => onSelect(vp)}
        >
          {vp.render_url && (
            <div className="result-render">
              <img
                src={`${BACKEND_URL}${vp.render_url}`}
                alt={`Terrain view from viewpoint #${vp.rank}`}
                loading="lazy"
              />
            </div>
          )}

          <div className="result-header">
            <span className="result-rank">#{vp.rank}</span>
            <span className="result-score">{vp.beauty_total.toFixed(3)}</span>
          </div>

          <div className="result-composition">
            {COMPOSITION_LABELS[vp.composition] || vp.composition}
          </div>

          <div className="result-coords">
            {vp.lat.toFixed(4)}N, {Math.abs(vp.lng).toFixed(4)}{vp.lng < 0 ? 'W' : 'E'} &middot;
            {' '}{vp.height_above_ground_m.toFixed(1)}m AGL &middot;
            {' '}{vp.heading_deg.toFixed(0)}° &middot;
            {' '}{vp.scene_type}
          </div>

          <div className="score-bars">
            {Object.entries(vp.beauty_scores).map(([key, value]) => {
              if (key === 'total') return null;
              return (
                <div key={key} className="score-bar">
                  <span className="score-bar-label">
                    {SCORE_LABELS[key] || key}
                  </span>
                  <div className="score-bar-track">
                    <div
                      className="score-bar-fill"
                      style={{ width: `${(value as number) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {vp.lighting && (
            <div className="result-lighting">
              <strong>{vp.lighting.best_time}</strong> — {vp.lighting.description}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
