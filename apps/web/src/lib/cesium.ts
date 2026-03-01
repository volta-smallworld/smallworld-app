import {
  Ion,
  CesiumTerrainProvider,
  Cesium3DTileset,
  IonImageryProvider,
  OpenStreetMapImageryProvider,
} from "cesium";

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
// Imagery providers
// ---------------------------------------------------------------------------

/**
 * Create an OpenStreetMap imagery provider.  Kept for backward compatibility
 * and as the fallback when no Ion token is available.
 */
export function createOsmImageryProvider() {
  return new OpenStreetMapImageryProvider({
    url: "https://tile.openstreetmap.org/",
  });
}

/**
 * Primary imagery provider used during normal map interaction.
 *
 * Always uses OpenStreetMap tiles to keep the interactive map token-free.
 * Ion imagery is only used in preview/scene-generation via createPreviewImageryProvider.
 */
export async function createPrimaryImageryProvider(): Promise<
  IonImageryProvider | OpenStreetMapImageryProvider
> {
  return createOsmImageryProvider();
}

/**
 * Imagery provider for preview / scene-generation pages.  Mirrors the primary
 * provider logic so previews match the main map experience.
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
 * Primary terrain provider for normal map interaction.
 *
 * Always returns undefined to keep the interactive map token-free (uses the WGS84
 * ellipsoid). Ion terrain is only used in preview/scene-generation via
 * createPreviewTerrainProvider.
 */
export async function createPrimaryTerrainProvider(): Promise<
  CesiumTerrainProvider | undefined
> {
  return undefined;
}

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
