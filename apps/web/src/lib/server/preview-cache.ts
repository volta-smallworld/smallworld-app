import { createHash } from "crypto";

interface CameraParams {
  lat: number;
  lng: number;
  altitudeMeters: number;
  headingDegrees: number;
  pitchDegrees: number;
  rollDegrees: number;
  fovDegrees: number;
}

interface CacheEntry {
  data: Buffer;
  timestamp: number;
}

const CACHE_MAX_ENTRIES = parseInt(
  process.env.PREVIEW_CACHE_MAX_ENTRIES || "24",
  10,
);
const CACHE_TTL_MS = parseInt(
  process.env.PREVIEW_CACHE_TTL_MS || "900000",
  10,
);

const cache = new Map<string, CacheEntry>();

/**
 * Creates a deterministic cache key by hashing sorted camera pose,
 * preview dimensions, and provider mode.
 */
export function getCacheKey(
  camera: CameraParams,
  width: number,
  height: number,
  provider: string,
): string {
  const params = {
    altitudeMeters: camera.altitudeMeters,
    fovDegrees: camera.fovDegrees,
    headingDegrees: camera.headingDegrees,
    height,
    lat: camera.lat,
    lng: camera.lng,
    pitchDegrees: camera.pitchDegrees,
    provider,
    rollDegrees: camera.rollDegrees,
    width,
  };

  const serialized = JSON.stringify(params);
  return createHash("sha256").update(serialized).digest("hex");
}

/**
 * Returns the cached preview buffer if the entry exists and has not expired.
 * Returns null if the key is missing or the entry has exceeded its TTL.
 */
export function getCachedPreview(key: string): Buffer | null {
  const entry = cache.get(key);
  if (!entry) {
    return null;
  }

  const age = Date.now() - entry.timestamp;
  if (age > CACHE_TTL_MS) {
    cache.delete(key);
    return null;
  }

  return entry.data;
}

/**
 * Stores a preview buffer in the cache with the current timestamp.
 * If the cache exceeds the maximum number of entries, the oldest
 * entry (by insertion order) is evicted.
 */
export function setCachedPreview(key: string, data: Buffer): void {
  // If key already exists, delete it first so it moves to the end
  // of the Map's insertion order when re-added.
  if (cache.has(key)) {
    cache.delete(key);
  }

  cache.set(key, { data, timestamp: Date.now() });

  // Evict oldest entries (first in insertion order) if over max
  while (cache.size > CACHE_MAX_ENTRIES) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey !== undefined) {
      cache.delete(oldestKey);
    }
  }
}

/**
 * Empties the entire preview cache.
 */
export function clearPreviewCache(): void {
  cache.clear();
}
