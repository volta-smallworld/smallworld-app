// Proxy path for quick requests (chat, export)
const API_BASE = '/api';

// Direct backend URL for long-running requests (analyze)
// Next.js proxy times out after ~30s, so we hit the backend directly
const BACKEND_URL = 'http://localhost:8000';

export interface Viewpoint {
  rank: number;
  lat: number;
  lng: number;
  altitude_m: number;
  height_above_ground_m: number;
  heading_deg: number;
  pitch_deg: number;
  fov_deg: number;
  composition: string;
  scene_type: string;
  beauty_scores: {
    viewshed_richness: number;
    viewpoint_entropy: number;
    skyline_fractal: number;
    prospect_refuge: number;
    depth_layering: number;
    mystery: number;
    water_visibility: number;
    total: number;
  };
  beauty_total: number;
  lighting: {
    best_time: string;
    best_score: number;
    description: string;
    secondary_time: string | null;
    secondary_score: number;
    timeline: [string, number][];
  } | null;
  render_url: string | null;
}

export interface AnalyzeRequest {
  center_lat: number;
  center_lng: number;
  radius_km?: number;
  mode?: 'ground' | 'drone';
  feature_weights?: Record<string, number>;
  beauty_weights?: Record<string, number>;
  composition_filter?: string[];
  max_results?: number;
  compute_lighting?: boolean;
}

export interface AnalyzeResponse {
  status: string;
  count: number;
  viewpoints: Viewpoint[];
}

export interface ChatResponse {
  response: string;
  results: Viewpoint[] | null;
}

export async function analyze(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  // Hit backend directly — this can take 60+ seconds for large areas
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300_000); // 5 min timeout

  try {
    const res = await fetch(`${BACKEND_URL}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal: controller.signal,
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => res.statusText);
      throw new Error(`Analysis failed: ${detail}`);
    }
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

export async function chat(message: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.statusText}`);
  return res.json();
}

export async function exportCSV(indices?: number[]): Promise<string> {
  const res = await fetch(`${API_BASE}/export/csv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ viewpoint_indices: indices }),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  return res.text();
}
