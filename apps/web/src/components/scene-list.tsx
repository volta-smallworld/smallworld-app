"use client";

import { SceneSeed } from "@/types/terrain";

interface SceneListProps {
  scenes: SceneSeed[];
}

const TYPE_COLORS: Record<string, string> = {
  "peak-water": "#3b82f6",
  "peak-ridge": "#d97706",
  "cliff-water": "#f97316",
  "multi-peak": "#eab308",
  "mixed-terrain": "#8b5cf6",
};

export default function SceneList({ scenes }: SceneListProps) {
  if (scenes.length === 0) return null;

  return (
    <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
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
        SCENES ({scenes.length})
      </div>
      {scenes.slice(0, 5).map((scene) => (
        <div
          key={scene.id}
          style={{
            padding: "8px 10px",
            borderRadius: 6,
            border: "1px solid rgba(255, 255, 255, 0.04)",
            backgroundColor: "rgba(255, 255, 255, 0.02)",
            fontSize: 12,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: 4,
            }}
          >
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: TYPE_COLORS[scene.type] || "#aaa",
              }}
            >
              {scene.type}
            </span>
            <span style={{ fontFamily: "monospace", fontSize: 12, color: "#a0a0a0" }}>
              {scene.score.toFixed(2)}
            </span>
          </div>
          <div style={{ fontSize: 11, color: "#666" }}>{scene.summary}</div>
          <div style={{ fontSize: 10, color: "#555", marginTop: 2 }}>
            {scene.featureIds.length} features
          </div>
        </div>
      ))}
    </div>
  );
}
