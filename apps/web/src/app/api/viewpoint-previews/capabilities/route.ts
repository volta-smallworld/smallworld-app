import { NextResponse } from "next/server";
import { getPreviewCapabilities } from "@/lib/server/preview-capabilities";
import { API_BASE_URL } from "@/lib/server/urls";

export const runtime = "nodejs";

type MapProvider = "google3d" | "ionTerrain" | "osm";

const API_TO_WEB_PROVIDER: Record<string, MapProvider> = {
  google_3d: "google3d",
  ion: "ionTerrain",
  osm: "osm",
};

export async function GET() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/previews/capabilities`, {
      signal: AbortSignal.timeout(3000),
    });

    if (res.ok) {
      const apiCaps = await res.json();

      const availableProviders = (apiCaps.availableProviders ?? [])
        .map((p: string) => API_TO_WEB_PROVIDER[p])
        .filter(Boolean);

      const providerOrder = (apiCaps.providerOrder ?? [])
        .map((p: string) => API_TO_WEB_PROVIDER[p])
        .filter(Boolean);

      const activeProvider = API_TO_WEB_PROVIDER[apiCaps.activeProvider] ?? "osm";

      return NextResponse.json({
        enabled: apiCaps.enabled,
        provider: activeProvider === "osm" && !apiCaps.enabled ? "none" : activeProvider,
        eagerCount: apiCaps.eagerCount ?? 0,
        message: apiCaps.message,
        availableProviders,
        providerOrder,
        activeProvider,
      });
    }
  } catch {
    // API unreachable — fall back to local capabilities
  }

  // Fallback to local resolution
  const capabilities = getPreviewCapabilities();
  return NextResponse.json(capabilities);
}
