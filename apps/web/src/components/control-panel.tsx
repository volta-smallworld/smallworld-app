"use client";

import { LatLng, TerrainFetchState } from "@/types/terrain";

interface ControlPanelProps {
  center: LatLng | null;
  radiusMeters: number;
  onRadiusChange: (radius: number) => void;
  onFetchTerrain: () => void;
  fetchState: TerrainFetchState;
}

export default function ControlPanel({
  center,
  radiusMeters,
  onRadiusChange,
  onFetchTerrain,
  fetchState,
}: ControlPanelProps) {
  const radiusKm = (radiusMeters / 1000).toFixed(1);

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 16 }}>
      <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Terrain Selection</h2>

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

      <button
        onClick={onFetchTerrain}
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
        {fetchState === "loading" ? "Fetching..." : "Fetch Terrain"}
      </button>
    </div>
  );
}
