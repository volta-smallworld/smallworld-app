import {
  ElevationGridRequest,
  ElevationGridResponse,
  TerrainAnalysisRequest,
  TerrainAnalysisResponse,
  ViewpointSearchRequest,
  ViewpointSearchResponse,
} from "@/types/terrain";
import { API_BASE_URL } from "@/lib/server/urls";
const API_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS || "45000");

function isAbortError(err: unknown): boolean {
  return (
    err instanceof DOMException &&
    err.name === "AbortError"
  );
}

async function fetchApiJson<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);

  try {
    const resp = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });

    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      const detail = body?.detail || resp.statusText;
      throw new Error(`API error ${resp.status}: ${detail}`);
    }

    return resp.json();
  } catch (err) {
    if (isAbortError(err)) {
      throw new Error(
        `Terrain analysis timed out after ${Math.round(API_TIMEOUT_MS / 1000)}s. Check API connectivity and try again.`,
      );
    }
    if (err instanceof TypeError) {
      throw new Error(
        `Could not reach API at ${API_BASE_URL}. Check NEXT_PUBLIC_API_BASE_URL and that the backend is running.`,
      );
    }
    throw err instanceof Error ? err : new Error(String(err));
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchElevationGrid(
  req: ElevationGridRequest
): Promise<ElevationGridResponse> {
  return fetchApiJson<ElevationGridResponse>("/api/v1/terrain/elevation-grid", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function analyzeTerrain(
  req: TerrainAnalysisRequest
): Promise<TerrainAnalysisResponse> {
  return fetchApiJson<TerrainAnalysisResponse>("/api/v1/terrain/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function findViewpoints(
  req: ViewpointSearchRequest
): Promise<ViewpointSearchResponse> {
  return fetchApiJson<ViewpointSearchResponse>("/api/v1/terrain/viewpoints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}
