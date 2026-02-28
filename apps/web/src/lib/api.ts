import {
  ElevationGridRequest,
  ElevationGridResponse,
  TerrainAnalysisRequest,
  TerrainAnalysisResponse,
} from "@/types/terrain";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function fetchElevationGrid(
  req: ElevationGridRequest
): Promise<ElevationGridResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/terrain/elevation-grid`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || resp.statusText;
    throw new Error(`API error ${resp.status}: ${detail}`);
  }
  return resp.json();
}

export async function analyzeTerrain(
  req: TerrainAnalysisRequest
): Promise<TerrainAnalysisResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/v1/terrain/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || resp.statusText;
    throw new Error(`API error ${resp.status}: ${detail}`);
  }
  return resp.json();
}
