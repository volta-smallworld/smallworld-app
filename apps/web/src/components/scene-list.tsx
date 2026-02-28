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
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
        Scene Seeds ({scenes.length})
      </h3>
      {scenes.slice(0, 5).map((scene) => (
        <div
          key={scene.id}
          style={{
            padding: "8px 10px",
            borderRadius: 6,
            border: `1px solid ${TYPE_COLORS[scene.type] || "#555"}`,
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
            <span
              style={{
                fontWeight: 600,
                color: TYPE_COLORS[scene.type] || "#aaa",
              }}
            >
              {scene.type}
            </span>
            <span style={{ fontFamily: "monospace", color: "#aaa" }}>
              {scene.score.toFixed(2)}
            </span>
          </div>
          <div style={{ color: "#999", fontSize: 12 }}>{scene.summary}</div>
          <div style={{ color: "#666", fontSize: 11, marginTop: 2 }}>
            {scene.featureIds.length} features
          </div>
        </div>
      ))}
    </div>
  );
}
