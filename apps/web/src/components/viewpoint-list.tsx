"use client";

import { RankedViewpoint } from "@/types/terrain";

interface ViewpointListProps {
  viewpoints: RankedViewpoint[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const COMP_COLORS: Record<string, string> = {
  ruleOfThirds: "#10b981",
  goldenRatio: "#f59e0b",
  leadingLine: "#8b5cf6",
  symmetry: "#ec4899",
};

export default function ViewpointList({
  viewpoints,
  selectedId,
  onSelect,
}: ViewpointListProps) {
  if (viewpoints.length === 0) return null;

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 8 }}>
      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
        Viewpoints ({viewpoints.length})
      </h3>
      {viewpoints.map((vp) => {
        const isSelected = vp.id === selectedId;
        const color = COMP_COLORS[vp.composition] || "#aaa";
        // Get top 3 score components
        const breakdown = vp.scoreBreakdown;
        const entries = Object.entries(breakdown) as [string, number][];
        const top3 = entries.sort((a, b) => b[1] - a[1]).slice(0, 3);

        return (
          <div
            key={vp.id}
            onClick={() => onSelect(vp.id)}
            style={{
              padding: "8px 10px",
              borderRadius: 6,
              border: `1px solid ${isSelected ? "#fff" : color}`,
              backgroundColor: isSelected ? "rgba(255,255,255,0.08)" : "transparent",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: 4,
              }}
            >
              <span style={{ fontWeight: 600, color }}>
                {vp.composition}
              </span>
              <span style={{ fontFamily: "monospace", color: "#aaa" }}>
                {vp.score.toFixed(2)}
              </span>
            </div>
            <div style={{ color: "#999", fontSize: 12 }}>
              {vp.sceneType} &middot; {vp.camera.altitudeMeters.toFixed(0)}m alt &middot; {vp.camera.headingDegrees.toFixed(0)}&deg;
            </div>
            <div style={{ color: "#666", fontSize: 11, marginTop: 2 }}>
              {vp.camera.lat.toFixed(4)}, {vp.camera.lng.toFixed(4)} &middot; pitch {vp.camera.pitchDegrees.toFixed(1)}&deg;
            </div>
            <div style={{ color: "#555", fontSize: 11, marginTop: 2 }}>
              {top3.map(([key, val]) => `${key}: ${val.toFixed(2)}`).join(" | ")}
            </div>
          </div>
        );
      })}
    </div>
  );
}
