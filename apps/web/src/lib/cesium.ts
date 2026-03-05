import {
  Ion,
  CesiumTerrainProvider,
  Cesium3DTileset,
  IonImageryProvider,
  OpenStreetMapImageryProvider,
} from "cesium";

export { OpenStreetMapImageryProvider };

let initialized = false;

/**
 * Returns the Cesium Ion access token from the environment, or an empty string
 * if none is configured.
 */
function getIonToken(): string {
  return process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN ?? "";
}

/**
 * Initialise global Cesium runtime settings.  Safe to call multiple times;
 * only the first invocation has any effect.
 *
 * - Sets `CESIUM_BASE_URL` so Workers / Assets / Widgets resolve correctly.
 * - If `NEXT_PUBLIC_CESIUM_ION_TOKEN` is set, configures Ion with that token.
 *   Otherwise falls back to token-free mode.
 */
export function initCesium() {
  if (initialized) return;
  (window as unknown as { CESIUM_BASE_URL: string }).CESIUM_BASE_URL = "/cesium/";

  const token = getIonToken();
  if (token) {
    Ion.defaultAccessToken = token;
  } else {
    Ion.defaultAccessToken = "";
  }

  initialized = true;
}

// ---------------------------------------------------------------------------
// Google Maps API key
// ---------------------------------------------------------------------------

function getGoogleMapsApiKey(): string {
  return process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";
}

/**
 * Returns `true` when a Google Maps API key is available, enabling
 * Google Photorealistic 3D Tiles for realistic terrain + imagery.
 */
export function hasGoogle3DTilesSupport(): boolean {
  return getGoogleMapsApiKey().length > 0;
}

/**
 * Create a Google Photorealistic 3D Tileset.  The tileset includes geometry,
 * terrain, and photorealistic textures — no separate terrain or imagery
 * provider is needed when this is active.
 */
export async function createGoogle3DTileset(
  apiKey?: string,
): Promise<Cesium3DTileset> {
  const key = apiKey || getGoogleMapsApiKey();
  if (!key) {
    throw new Error("Google Maps API key is required for 3D tiles");
  }
  const url = `https://tile.googleapis.com/v1/3dtiles/root.json?key=${key}`;
  return Cesium3DTileset.fromUrl(url);
}

// ---------------------------------------------------------------------------
// Capability detection
// ---------------------------------------------------------------------------

/**
 * Returns `true` when an Ion token is available, which unlocks Cesium World
 * Terrain and Bing Maps aerial imagery for richer preview rendering.
 */
export function hasPreviewTerrainSupport(): boolean {
  return getIonToken().length > 0;
}

// ---------------------------------------------------------------------------
// Provider resolution
// ---------------------------------------------------------------------------

export type MapProvider = "google3d" | "ionTerrain" | "osm";

export interface ProviderResolution {
  activeProvider: MapProvider;
  availableProviders: MapProvider[];
  providerOrder: MapProvider[];
}

/**
 * Resolve the active map provider based on available API keys / tokens.
 *
 * Priority: google3d > ionTerrain > osm
 *
 * - `google3d`    — `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is set
 * - `ionTerrain`  — `NEXT_PUBLIC_CESIUM_ION_TOKEN` is set
 * - `osm`         — always available (no key required)
 *
 * The result is deterministic: same env vars always produce the same output.
 */
export function resolveMapProvider(): ProviderResolution {
  const providerOrder: MapProvider[] = ["google3d", "ionTerrain", "osm"];
  const available: MapProvider[] = [];

  if (getGoogleMapsApiKey()) available.push("google3d");
  if (getIonToken()) available.push("ionTerrain");
  available.push("osm"); // always available

  const activeProvider = available[0];

  return {
    activeProvider,
    availableProviders: available,
    providerOrder,
  };
}

// ---------------------------------------------------------------------------
// Imagery providers
// ---------------------------------------------------------------------------

/**
 * Create an OpenStreetMap imagery provider.  Used as base layer for the
 * interactive map and as fallback when no Ion token is available.
 */
export function createOsmImageryProvider() {
  return new OpenStreetMapImageryProvider({
    url: "https://tile.openstreetmap.org/",
  });
}

/**
 * Imagery provider for preview / scene-generation pages.
 *
 * - **Ion token set** -> Bing Maps aerial via `IonImageryProvider` (asset 2).
 * - **No token**      -> OpenStreetMap tiles.
 */
export async function createPreviewImageryProvider(): Promise<
  IonImageryProvider | OpenStreetMapImageryProvider
> {
  if (hasPreviewTerrainSupport()) {
    return IonImageryProvider.fromAssetId(2);
  }
  return createOsmImageryProvider();
}

// ---------------------------------------------------------------------------
// Terrain providers
// ---------------------------------------------------------------------------

/**
 * Terrain provider for preview / scene-generation pages.  Uses Ion terrain
 * when available so previews render realistic elevation; falls back to
 * `undefined` (ellipsoid) otherwise.
 */
export async function createPreviewTerrainProvider(): Promise<
  CesiumTerrainProvider | undefined
> {
  if (hasPreviewTerrainSupport()) {
    return CesiumTerrainProvider.fromIonAssetId(1);
  }
  return undefined;
}
