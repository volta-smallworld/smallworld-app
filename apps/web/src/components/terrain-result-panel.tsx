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

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "3px 0",
        fontSize: 13,
      }}
    >
      <span style={{ color: "#888" }}>{label}</span>
      <span style={{ fontFamily: "monospace" }}>{value}</span>
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
      <div style={{ padding: 16, color: "#aaa" }}>Analyzing terrain...</div>
    );
  }

  if (fetchState === "error") {
    return (
      <div style={{ padding: 16, color: "#ef4444" }}>
        <strong>Error:</strong> {error}
      </div>
    );
  }

  if (!result) return null;

  const { summary, features, hotspots } = result;

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Analysis Results</h3>

      {/* Summary stats */}
      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Elevation</div>
        <Row label="Min" value={`${summary.elevationMeters.min} m`} />
        <Row label="Max" value={`${summary.elevationMeters.max} m`} />
        <Row label="Mean" value={`${summary.elevationMeters.mean} m`} />
      </div>

      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Slope</div>
        <Row label="Max" value={`${summary.slopeDegrees.max}\u00b0`} />
        <Row label="Mean" value={`${summary.slopeDegrees.mean}\u00b0`} />
      </div>

      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Local Relief</div>
        <Row label="Max" value={`${summary.localReliefMeters.max} m`} />
        <Row label="Mean" value={`${summary.localReliefMeters.mean} m`} />
      </div>

      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Interest</div>
        <Row label="Max" value={summary.interestScore.max.toFixed(2)} />
        <Row label="Mean" value={summary.interestScore.mean.toFixed(2)} />
      </div>

      {/* Feature counts */}
      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Features</div>
        <Row label="Peaks" value={features.peaks.length} />
        <Row label="Ridges" value={features.ridges.length} />
        <Row label="Cliffs" value={features.cliffs.length} />
        <Row label="Water" value={features.waterChannels.length} />
        <Row label="Hotspots" value={hotspots.length} />
      </div>

      {/* Top peaks */}
      {features.peaks.length > 0 && (
        <div>
          <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Top Peaks</div>
          {features.peaks.slice(0, 5).map((p) => (
            <Row
              key={p.id}
              label={`${p.elevationMeters?.toFixed(0)} m`}
              value={`prom ~${p.prominenceMetersApprox?.toFixed(0)} m`}
            />
          ))}
        </div>
      )}

      {/* Top hotspots */}
      {hotspots.length > 0 && (
        <div>
          <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Top Hotspots</div>
          {hotspots.slice(0, 5).map((h) => (
            <Row
              key={h.id}
              label={h.reasons.join(", ")}
              value={h.score.toFixed(2)}
            />
          ))}
        </div>
      )}

      {/* Grid info */}
      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Grid</div>
        <Row label="Size" value={`${result.grid.width} x ${result.grid.height}`} />
        <Row label="Cell size" value={`~${result.grid.cellSizeMetersApprox} m`} />
        <Row label="Zoom" value={result.request.zoomUsed} />
        <Row label="Tiles" value={result.tiles.length} />
      </div>

      <div style={{ fontSize: 11, color: "#666" }}>Source: {result.source}</div>
    </div>
  );
}
