"use client";

import {
  LatLng,
  AnalysisWeights,
  AnalysisOverlayKey,
  TerrainFetchState,
  CompositionType,
  ViewpointFetchState,
} from "@/types/terrain";

const WEIGHT_KEYS: { key: keyof AnalysisWeights; label: string }[] = [
  { key: "peaks", label: "Peaks" },
  { key: "ridges", label: "Ridges" },
  { key: "cliffs", label: "Cliffs" },
  { key: "water", label: "Water" },
  { key: "relief", label: "Relief" },
];

const OVERLAY_KEYS: { key: AnalysisOverlayKey; label: string; color: string }[] = [
  { key: "peaks", label: "Peaks", color: "#eab308" },
  { key: "ridges", label: "Ridges", color: "#d97706" },
  { key: "cliffs", label: "Cliffs", color: "#f97316" },
  { key: "waterChannels", label: "Water", color: "#3b82f6" },
  { key: "hotspots", label: "Hotspots", color: "#06b6d4" },
  { key: "viewpoints", label: "Viewpoints", color: "#d946ef" },
];

const COMPOSITION_OPTIONS: { key: CompositionType; label: string; color: string }[] = [
  { key: "ruleOfThirds", label: "Rule of 3rds", color: "#10b981" },
  { key: "goldenRatio", label: "Golden Ratio", color: "#f59e0b" },
  { key: "leadingLine", label: "Leading Line", color: "#8b5cf6" },
  { key: "symmetry", label: "Symmetry", color: "#ec4899" },
];

interface ControlPanelProps {
  center: LatLng | null;
  radiusMeters: number;
  onRadiusChange: (radius: number) => void;
  weights: AnalysisWeights;
  onWeightsChange: (weights: AnalysisWeights) => void;
  overlays: Record<AnalysisOverlayKey, boolean>;
  onToggleOverlay: (key: AnalysisOverlayKey) => void;
  onAnalyze: () => void;
  fetchState: TerrainFetchState;
  selectedCompositions: CompositionType[];
  onCompositionsChange: (compositions: CompositionType[]) => void;
  onFindViewpoints: () => void;
  viewpointFetchState: ViewpointFetchState;
}

export default function ControlPanel({
  center,
  radiusMeters,
  onRadiusChange,
  weights,
  onWeightsChange,
  overlays,
  onToggleOverlay,
  onAnalyze,
  fetchState,
  selectedCompositions,
  onCompositionsChange,
  onFindViewpoints,
  viewpointFetchState,
}: ControlPanelProps) {
  const radiusKm = (radiusMeters / 1000).toFixed(1);

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Terrain Analysis</h2>

      <div>
        <label style={{ fontSize: 13, color: "#888" }}>Selected Point</label>
        {center ? (
          <div style={{ fontFamily: "monospace", fontSize: 14 }}>
            {center.lat.toFixed(4)}, {center.lng.toFixed(4)}
          </div>
        ) : (
          <div style={{ fontSize: 14, color: "#666" }}>Click the globe to select</div>
        )}
      </div>

      <div>
        <label style={{ fontSize: 13, color: "#888" }}>
          Radius: {radiusKm} km ({radiusMeters.toLocaleString()} m)
        </label>
        <input
          type="range"
          min={1000}
          max={50000}
          step={500}
          value={radiusMeters}
          onChange={(e) => onRadiusChange(Number(e.target.value))}
          style={{ width: "100%", marginTop: 4 }}
        />
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 11,
            color: "#888",
          }}
        >
          <span>1 km</span>
          <span>50 km</span>
        </div>
      </div>

      {/* Weight sliders */}
      <div>
        <div style={{ fontSize: 13, color: "#888", marginBottom: 6 }}>Weights</div>
        {WEIGHT_KEYS.map(({ key, label }) => (
          <div key={key} style={{ marginBottom: 6 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 12,
                color: "#aaa",
              }}
            >
              <span>{label}</span>
              <span style={{ fontFamily: "monospace" }}>{weights[key].toFixed(2)}</span>
            </div>
            <input
              type="range"
              min={0}
              max={2}
              step={0.25}
              value={weights[key]}
              onChange={(e) =>
                onWeightsChange({ ...weights, [key]: Number(e.target.value) })
              }
              style={{ width: "100%", marginTop: 2 }}
            />
          </div>
        ))}
      </div>

      {/* Overlay toggles */}
      <div>
        <div style={{ fontSize: 13, color: "#888", marginBottom: 6 }}>Overlays</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {OVERLAY_KEYS.map(({ key, label, color }) => (
            <button
              key={key}
              onClick={() => onToggleOverlay(key)}
              style={{
                padding: "4px 10px",
                fontSize: 12,
                fontWeight: 500,
                border: `1px solid ${color}`,
                borderRadius: 4,
                cursor: "pointer",
                backgroundColor: overlays[key] ? color : "transparent",
                color: overlays[key] ? "#000" : color,
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={onAnalyze}
        disabled={!center || fetchState === "loading"}
        style={{
          padding: "10px 16px",
          fontSize: 14,
          fontWeight: 600,
          backgroundColor: !center || fetchState === "loading" ? "#444" : "#2563eb",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          cursor: !center || fetchState === "loading" ? "not-allowed" : "pointer",
        }}
      >
        {fetchState === "loading" ? "Analyzing..." : "Analyze Terrain"}
      </button>

      {/* Composition selection */}
      <div>
        <div style={{ fontSize: 13, color: "#888", marginBottom: 6 }}>Compositions</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {COMPOSITION_OPTIONS.map(({ key, label, color }) => {
            const active = selectedCompositions.includes(key);
            return (
              <button
                key={key}
                onClick={() => {
                  if (active) {
                    onCompositionsChange(selectedCompositions.filter((c) => c !== key));
                  } else {
                    onCompositionsChange([...selectedCompositions, key]);
                  }
                }}
                style={{
                  padding: "4px 10px",
                  fontSize: 12,
                  fontWeight: 500,
                  border: `1px solid ${color}`,
                  borderRadius: 4,
                  cursor: "pointer",
                  backgroundColor: active ? color : "transparent",
                  color: active ? "#000" : color,
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <button
        onClick={onFindViewpoints}
        disabled={fetchState !== "success" || viewpointFetchState === "loading" || selectedCompositions.length === 0}
        style={{
          padding: "10px 16px",
          fontSize: 14,
          fontWeight: 600,
          backgroundColor:
            fetchState !== "success" || viewpointFetchState === "loading" || selectedCompositions.length === 0
              ? "#444"
              : "#059669",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          cursor:
            fetchState !== "success" || viewpointFetchState === "loading" || selectedCompositions.length === 0
              ? "not-allowed"
              : "pointer",
        }}
      >
        {viewpointFetchState === "loading" ? "Finding Viewpoints..." : "Find Viewpoints"}
      </button>
    </div>
  );
}
