"use client";

import {
  ElevationGridResponse,
  TerrainFetchState,
} from "@/types/terrain";

interface TerrainResultPanelProps {
  fetchState: TerrainFetchState;
  result: ElevationGridResponse | null;
  error: string | null;
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "4px 0",
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
      <div style={{ padding: 16, color: "#aaa" }}>Loading elevation data...</div>
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

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Elevation Results</h3>

      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Stats</div>
        <Row label="Min" value={`${result.stats.minElevation} m`} />
        <Row label="Max" value={`${result.stats.maxElevation} m`} />
        <Row label="Mean" value={`${result.stats.meanElevation} m`} />
      </div>

      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Grid</div>
        <Row label="Size" value={`${result.grid.width} x ${result.grid.height}`} />
        <Row label="Cell size" value={`~${result.grid.cellSizeMetersApprox} m`} />
      </div>

      <div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>Coverage</div>
        <Row label="Zoom" value={result.request.zoomUsed} />
        <Row label="Tiles" value={result.tiles.length} />
        <Row label="North" value={result.bounds.north.toFixed(4)} />
        <Row label="South" value={result.bounds.south.toFixed(4)} />
        <Row label="East" value={result.bounds.east.toFixed(4)} />
        <Row label="West" value={result.bounds.west.toFixed(4)} />
      </div>

      <div style={{ fontSize: 11, color: "#666" }}>Source: {result.source}</div>
    </div>
  );
}
