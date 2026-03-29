import { NextRequest, NextResponse } from "next/server";
import { getPreviewCapabilities } from "@/lib/server/preview-capabilities";
// @deprecated renderPreview from "@/lib/server/preview-renderer" — use API delegation instead
import { getCacheKey, getCachedPreview, setCachedPreview } from "@/lib/server/preview-cache";
import { API_BASE_URL } from "@/lib/server/urls";

export const runtime = "nodejs";

interface CameraInput {
  lat: number;
  lng: number;
  altitudeMeters: number;
  headingDegrees: number;
  pitchDegrees: number;
  rollDegrees: number;
  fovDegrees: number;
}

function validateCamera(camera: unknown): { valid: true; camera: CameraInput } | { valid: false; error: string } {
  if (!camera || typeof camera !== "object") {
    return { valid: false, error: "Missing camera object" };
  }

  const c = camera as Record<string, unknown>;

  const requiredFields = ["lat", "lng", "altitudeMeters", "headingDegrees", "pitchDegrees", "rollDegrees", "fovDegrees"];
  for (const field of requiredFields) {
    if (typeof c[field] !== "number" || !Number.isFinite(c[field] as number)) {
      return { valid: false, error: `Invalid or missing field: ${field}` };
    }
  }

  const lat = c.lat as number;
  const lng = c.lng as number;
  const altitudeMeters = c.altitudeMeters as number;
  const fovDegrees = c.fovDegrees as number;

  if (lat < -90 || lat > 90) return { valid: false, error: "lat must be in [-90, 90]" };
  if (lng < -180 || lng > 180) return { valid: false, error: "lng must be in [-180, 180]" };
  if (altitudeMeters <= 0) return { valid: false, error: "altitudeMeters must be > 0" };
  if (fovDegrees < 20 || fovDegrees > 120) return { valid: false, error: "fovDegrees must be in [20, 120]" };

  return {
    valid: true,
    camera: {
      lat,
      lng,
      altitudeMeters,
      headingDegrees: c.headingDegrees as number,
      pitchDegrees: c.pitchDegrees as number,
      rollDegrees: c.rollDegrees as number,
      fovDegrees,
    },
  };
}

function logPreviewEvent(event: string, context: Record<string, unknown>) {
  const entry = {
    ts: new Date().toISOString(),
    component: "viewpoint-previews",
    event,
    ...context,
  };
  process.stderr.write(JSON.stringify(entry) + "\n");
}

export async function POST(request: NextRequest) {
  const startMs = Date.now();

  // Check capability
  const capabilities = getPreviewCapabilities();
  if (!capabilities.enabled) {
    return NextResponse.json(
      { error: "Preview capability unavailable", message: capabilities.message },
      { status: 503 }
    );
  }

  // Parse body
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 422 });
  }

  const viewpointId = typeof body.viewpointId === "string" ? body.viewpointId : undefined;

  // Validate
  const validation = validateCamera(body.camera);
  if (!validation.valid) {
    return NextResponse.json({ error: validation.error }, { status: 422 });
  }

  const { camera } = validation;
  const RENDER_WIDTH = parseInt(process.env.PREVIEW_RENDER_WIDTH || "1280", 10);
  const RENDER_HEIGHT = parseInt(process.env.PREVIEW_RENDER_HEIGHT || "720", 10);

  logPreviewEvent("request", { viewpointId, provider: capabilities.provider });

  // Check cache
  const cacheKey = getCacheKey(camera, RENDER_WIDTH, RENDER_HEIGHT, capabilities.provider);
  const cached = getCachedPreview(cacheKey);
  if (cached) {
    logPreviewEvent("cache_hit", { viewpointId, durationMs: Date.now() - startMs });
    return new NextResponse(new Uint8Array(cached), {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "X-Smallworld-Preview-Cache": "hit",
      },
    });
  }

  // Delegate to API pipeline
  try {
    const renderRequest = {
      camera: {
        position: {
          lat: camera.lat,
          lng: camera.lng,
          altMeters: camera.altitudeMeters,
        },
        headingDeg: camera.headingDegrees,
        pitchDeg: camera.pitchDegrees,
        rollDeg: camera.rollDegrees,
        fovDeg: camera.fovDegrees,
      },
      viewport: { width: RENDER_WIDTH, height: RENDER_HEIGHT },
      scene: {
        center: { lat: camera.lat, lng: camera.lng },
        radiusMeters: 5000,
      },
      composition: { targetTemplate: "custom" },
      enhancement: { enabled: false },
    };

    const renderRes = await fetch(`${API_BASE_URL}/api/v1/previews/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(renderRequest),
    });

    if (!renderRes.ok) {
      const errorData = await renderRes.json().catch(() => ({ detail: "Unknown API error" }));
      const detail = errorData.detail || errorData.message || `API error ${renderRes.status}`;
      logPreviewEvent("render_error", {
        viewpointId,
        status: renderRes.status,
        detail,
        durationMs: Date.now() - startMs,
      });

      // Map API error codes to appropriate responses
      if (renderRes.status === 503) {
        return NextResponse.json({ error: "Preview render backend unavailable", detail }, { status: 503 });
      }
      if (renderRes.status === 504) {
        return NextResponse.json({ error: "Preview render timed out", detail }, { status: 504 });
      }
      if (renderRes.status === 502) {
        return NextResponse.json({ error: "Preview render failed", detail }, { status: 502 });
      }
      return NextResponse.json({ error: "Preview render failed", detail }, { status: 502 });
    }

    const renderData = await renderRes.json();

    // Fetch the raw artifact image from the API
    if (!renderData.rawImage?.url) {
      logPreviewEvent("render_error", {
        viewpointId,
        detail: "No rawImage URL in render response",
        durationMs: Date.now() - startMs,
      });
      return NextResponse.json(
        { error: "Preview render produced no image" },
        { status: 502 }
      );
    }

    const artifactRes = await fetch(`${API_BASE_URL}${renderData.rawImage.url}`);
    if (!artifactRes.ok) {
      logPreviewEvent("render_error", {
        viewpointId,
        detail: `Artifact fetch failed: ${artifactRes.status}`,
        durationMs: Date.now() - startMs,
      });
      return NextResponse.json(
        { error: "Failed to fetch preview artifact" },
        { status: 502 }
      );
    }

    const imageBuffer = Buffer.from(await artifactRes.arrayBuffer());
    setCachedPreview(cacheKey, imageBuffer);

    logPreviewEvent("render_success", {
      viewpointId,
      provider: capabilities.provider,
      durationMs: Date.now() - startMs,
    });

    return new NextResponse(new Uint8Array(imageBuffer), {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "X-Smallworld-Preview-Cache": "miss",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    logPreviewEvent("render_error", {
      viewpointId,
      detail: message,
      durationMs: Date.now() - startMs,
    });

    // Network errors -> 502 (API unreachable)
    return NextResponse.json({ error: "Preview render failed", detail: message }, { status: 502 });
  }
}
