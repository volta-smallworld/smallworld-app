import { NextRequest, NextResponse } from "next/server";
import { getPreviewCapabilities } from "@/lib/server/preview-capabilities";
import { renderPreview } from "@/lib/server/preview-renderer";
import { getCacheKey, getCachedPreview, setCachedPreview } from "@/lib/server/preview-cache";

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

export async function POST(request: NextRequest) {
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

  // Validate
  const validation = validateCamera(body.camera);
  if (!validation.valid) {
    return NextResponse.json({ error: validation.error }, { status: 422 });
  }

  const { camera } = validation;
  const RENDER_WIDTH = parseInt(process.env.PREVIEW_RENDER_WIDTH || "1280", 10);
  const RENDER_HEIGHT = parseInt(process.env.PREVIEW_RENDER_HEIGHT || "720", 10);

  // Check cache
  const cacheKey = getCacheKey(camera, RENDER_WIDTH, RENDER_HEIGHT, capabilities.provider);
  const cached = getCachedPreview(cacheKey);
  if (cached) {
    return new NextResponse(new Uint8Array(cached), {
      status: 200,
      headers: {
        "Content-Type": "image/jpeg",
        "X-Smallworld-Preview-Cache": "hit",
      },
    });
  }

  // Render
  try {
    const imageBuffer = await renderPreview(camera);
    setCachedPreview(cacheKey, imageBuffer);

    return new NextResponse(new Uint8Array(imageBuffer), {
      status: 200,
      headers: {
        "Content-Type": "image/jpeg",
        "X-Smallworld-Preview-Cache": "miss",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);

    if (message.includes("timeout") || message.includes("Timeout")) {
      return NextResponse.json({ error: "Preview render timed out", message }, { status: 504 });
    }

    return NextResponse.json({ error: "Preview render failed", message }, { status: 500 });
  }
}
