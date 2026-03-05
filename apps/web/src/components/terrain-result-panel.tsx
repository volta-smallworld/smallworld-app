"use client";

import {
  TerrainAnalysisResponse,
  TerrainFetchState,
} from "@/types/terrain";

interface TerrainResultPanelProps {
  fetchState: TerrainFetchState;
  result: TerrainAnalysisResponse | null;
  error: string | null;
}

function StatBox({
  label,
  min,
  max,
  mean,
  unit,
}: {
  label: string;
  min?: number;
  max: number;
  mean: number;
  unit: string;
}) {
  return (
    <div
      style={{
        padding: "8px 10px",
        borderRadius: 6,
        backgroundColor: "rgba(255, 255, 255, 0.03)",
        border: "1px solid rgba(255, 255, 255, 0.04)",
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "#555",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: "monospace",
          fontSize: 14,
          color: "#d0d0d0",
          fontWeight: 600,
        }}
      >
        {max}{unit}
      </div>
      <div style={{ fontSize: 10, color: "#555", marginTop: 2 }}>
        {min !== undefined ? `${min}${unit} min · ` : ""}{mean}{unit} avg
      </div>
    </div>
  );
}

export default function TerrainResultPanel({
  fetchState,
  result,
  error,
}: TerrainResultPanelProps) {
  if (fetchState === "idle") return null;

  if (fetchState === "loading") {
    return (
      <div style={{ padding: "14px 16px", color: "#aaa" }}>
        Analyzing terrain...
      </div>
    );
  }

  if (fetchState === "error") {
    return (
      <div style={{ padding: "14px 16px", color: "#ef4444" }}>
        <strong>Error:</strong> {error}
      </div>
    );
  }

  if (!result) return null;

  const { summary, features, hotspots } = result;

  return (
    <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "#555",
          marginBottom: 10,
        }}
      >
        ANALYSIS RESULTS
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <StatBox
          label="Elevation"
          min={summary.elevationMeters.min}
          max={summary.elevationMeters.max}
          mean={summary.elevationMeters.mean}
          unit="m"
        />
        <StatBox
          label="Slope"
          max={summary.slopeDegrees.max}
          mean={summary.slopeDegrees.mean}
          unit="°"
        />
        <StatBox
          label="Relief"
          max={summary.localReliefMeters.max}
          mean={summary.localReliefMeters.mean}
          unit="m"
        />
        <StatBox
          label="Interest"
          max={summary.interestScore.max}
          mean={summary.interestScore.mean}
          unit=""
        />
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
        {[
          { label: "Peaks", count: features.peaks.length, color: "#eab308" },
          { label: "Ridges", count: features.ridges.length, color: "#d97706" },
          { label: "Cliffs", count: features.cliffs.length, color: "#f97316" },
          { label: "Water", count: features.waterChannels.length, color: "#3b82f6" },
          { label: "Hotspots", count: hotspots.length, color: "#06b6d4" },
        ].map(({ label, count, color }) => (
          <div
            key={label}
            style={{
              padding: "3px 8px",
              borderRadius: 4,
              backgroundColor: color + "15",
              border: `1px solid ${color}30`,
              fontSize: 11,
              color: color,
            }}
          >
            {count} {label}
          </div>
        ))}
      </div>
    </div>
  );
}
