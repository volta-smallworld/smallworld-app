import asyncio
import io
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx
import numpy as np
from PIL import Image
from scipy.ndimage import zoom as ndimage_zoom

from smallworld_api.config import settings
from smallworld_api.services.tiles import (
    GeoBounds,
    TileRange,
    _lat_to_tile_y_frac,
    _lng_to_tile_x_frac,
    bounds_to_tile_range,
    center_radius_to_bounds,
    tile_bounds,
)

TILE_SIZE = 256
GRID_SIZE = 128
TILE_FETCH_CONCURRENCY = 8


# ── LRU tile cache with TTL expiry ────────────────────────────────────────


class _TileCache:
    """Thread-safe LRU cache for decoded elevation arrays keyed by (z, x, y).

    Entries are evicted when the cache exceeds *max_size* or when their age
    exceeds *ttl_seconds*.
    """

    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        # OrderedDict preserves insertion order; we move-to-end on access
        self._store: OrderedDict[tuple[int, int, int], tuple[float, np.ndarray]] = (
            OrderedDict()
        )

    # ── public API ────────────────────────────────────────────────────────

    def get(self, key: tuple[int, int, int]) -> np.ndarray | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, arr = entry
            if (time.monotonic() - ts) > self._ttl:
                # expired
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return arr

    def put(self, key: tuple[int, int, int], arr: np.ndarray) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._store[key] = (time.monotonic(), arr)
            else:
                self._store[key] = (time.monotonic(), arr)
                if len(self._store) > self._max_size:
                    self._store.popitem(last=False)  # evict LRU

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_tile_cache = _TileCache(
    max_size=settings.tile_cache_max_size,
    ttl_seconds=settings.tile_cache_ttl_seconds,
)


def decode_terrarium(img: Image.Image) -> np.ndarray:
    """Decode a Terrarium PNG into elevation in meters.

    Formula: elevation = (R * 256 + G + B / 256) - 32768
    """
    arr = np.asarray(img, dtype=np.float64)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    return (r * 256.0 + g + b / 256.0) - 32768.0


async def fetch_tile(client: httpx.AsyncClient, z: int, x: int, y: int) -> Image.Image:
    """Fetch a single Terrarium tile and return as a PIL Image."""
    url = settings.terrarium_tile_url_template.format(z=z, x=x, y=y)
    resp = await client.get(url, timeout=15.0)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


async def fetch_tile_decoded(
    client: httpx.AsyncClient, z: int, x: int, y: int
) -> np.ndarray:
    """Fetch and decode a tile, returning the cached elevation array when possible."""
    key = (z, x, y)
    cached = _tile_cache.get(key)
    if cached is not None:
        return cached
    img = await fetch_tile(client, z, x, y)
    elev = decode_terrarium(img)
    _tile_cache.put(key, elev)
    return elev


async def fetch_and_stitch(
    client: httpx.AsyncClient, tile_range: TileRange
) -> tuple[np.ndarray, GeoBounds]:
    """Fetch all tiles in a range, decode, and stitch into a single elevation array.

    Returns the stitched elevation array and the geographic bounds of the mosaic.
    Uses the tile cache to avoid redundant fetches.
    """
    cols = tile_range.x_max - tile_range.x_min + 1
    rows = tile_range.y_max - tile_range.y_min + 1
    mosaic = np.zeros((rows * TILE_SIZE, cols * TILE_SIZE), dtype=np.float64)

    tile_coords = tile_range.tile_coords()
    semaphore = asyncio.Semaphore(TILE_FETCH_CONCURRENCY)

    async def _fetch_decode(z: int, x: int, y: int) -> tuple[int, int, int, np.ndarray]:
        async with semaphore:
            elev = await fetch_tile_decoded(client, z, x, y)
        return z, x, y, elev

    tile_results = await asyncio.gather(
        *(_fetch_decode(z, x, y) for z, x, y in tile_coords)
    )

    for z, x, y, elev in tile_results:
        row_offset = (y - tile_range.y_min) * TILE_SIZE
        col_offset = (x - tile_range.x_min) * TILE_SIZE
        mosaic[row_offset : row_offset + TILE_SIZE, col_offset : col_offset + TILE_SIZE] = elev

    # Compute mosaic geographic bounds
    nw = tile_bounds(tile_range.z, tile_range.x_min, tile_range.y_min)
    se = tile_bounds(tile_range.z, tile_range.x_max, tile_range.y_max)
    mosaic_bounds = GeoBounds(
        north=nw.north, south=se.south, east=se.east, west=nw.west
    )
    return mosaic, mosaic_bounds


def crop_and_resample(
    mosaic: np.ndarray,
    mosaic_bounds: GeoBounds,
    target_bounds: GeoBounds,
    grid_size: int = GRID_SIZE,
) -> np.ndarray:
    """Crop the mosaic to target bounds and resample to a fixed grid using bilinear interpolation."""
    h, w = mosaic.shape

    # Map target bounds to pixel coordinates in the mosaic
    lng_range = mosaic_bounds.east - mosaic_bounds.west
    lat_range = mosaic_bounds.north - mosaic_bounds.south

    col_start = int((target_bounds.west - mosaic_bounds.west) / lng_range * w)
    col_end = int((target_bounds.east - mosaic_bounds.west) / lng_range * w)
    row_start = int((mosaic_bounds.north - target_bounds.north) / lat_range * h)
    row_end = int((mosaic_bounds.north - target_bounds.south) / lat_range * h)

    # Clamp to array bounds
    col_start = max(0, col_start)
    col_end = min(w, col_end)
    row_start = max(0, row_start)
    row_end = min(h, row_end)

    cropped = mosaic[row_start:row_end, col_start:col_end]

    if cropped.size == 0:
        return np.zeros((grid_size, grid_size), dtype=np.float64)

    # Resample to grid_size x grid_size using bilinear interpolation (order=1)
    crop_h, crop_w = cropped.shape
    if crop_h == 0 or crop_w == 0:
        return np.zeros((grid_size, grid_size), dtype=np.float64)

    zoom_factors = (grid_size / crop_h, grid_size / crop_w)
    return ndimage_zoom(cropped, zoom_factors, order=1)


def compute_cell_size_meters(bounds: GeoBounds, grid_size: int) -> float:
    """Approximate cell size in meters for the grid."""
    earth_radius = 6378137.0
    mid_lat = (bounds.north + bounds.south) / 2
    ns_m = math.radians(bounds.north - bounds.south) * earth_radius
    ew_m = math.radians(bounds.east - bounds.west) * earth_radius * math.cos(math.radians(mid_lat))
    avg_span = (ns_m + ew_m) / 2
    return round(avg_span / grid_size, 1)


@dataclass
class DEMSnapshot:
    """Raw DEM grid with metadata — shared between elevation-grid and analysis."""

    dem: np.ndarray  # 128x128 elevation in meters
    bounds: GeoBounds
    tile_coords: list[tuple[int, int, int]]
    zoom: int
    cell_size_meters: float
    zoom_requested: int = 0  # original zoom before adaptive downshift


def _resolve_tile_range(
    target_bounds: GeoBounds,
    zoom: int | None = None,
) -> tuple[TileRange, int]:
    """Choose the highest zoom that stays within the server tile cap.

    Returns a (tile_range, zoom_requested) tuple so callers can report
    both the originally requested zoom and the zoom actually used.
    """
    requested_zoom = zoom or settings.default_terrarium_zoom

    for candidate_zoom in range(requested_zoom, -1, -1):
        tile_range = bounds_to_tile_range(target_bounds, candidate_zoom)
        if tile_range.tile_count <= settings.max_tiles_per_request:
            return tile_range, requested_zoom

    raise ValueError(
        f"Request covers more than {settings.max_tiles_per_request} tiles even at the lowest supported zoom. "
        f"Try a smaller radius."
    )


async def fetch_dem_snapshot(
    lat: float, lng: float, radius_m: float, zoom: int | None = None
) -> DEMSnapshot:
    """Fetch tiles, decode, stitch, crop, and resample into a 128x128 DEM grid."""
    target_bounds = center_radius_to_bounds(lat, lng, radius_m)
    tile_range, zoom_requested = _resolve_tile_range(target_bounds, zoom)

    async with httpx.AsyncClient() as client:
        mosaic, mosaic_bounds = await fetch_and_stitch(client, tile_range)

    grid = crop_and_resample(mosaic, mosaic_bounds, target_bounds, GRID_SIZE)

    return DEMSnapshot(
        dem=grid,
        bounds=target_bounds,
        tile_coords=tile_range.tile_coords(),
        zoom=tile_range.z,
        cell_size_meters=compute_cell_size_meters(target_bounds, GRID_SIZE),
        zoom_requested=zoom_requested,
    )


@dataclass
class PointElevationResult:
    """Result of sampling a single point at full tile resolution."""

    elevation_meters: float
    lat: float
    lng: float
    zoom: int
    tile_coords: list[tuple[int, int, int]]
    meters_per_pixel_approx: float


async def sample_point_elevation(
    lat: float, lng: float, zoom: int | None = None
) -> PointElevationResult:
    """Sample elevation at a single lat/lng at full tile resolution.

    Uses bilinear interpolation across raw 256x256 tiles — never touches the
    128x128 resampled grid.  Fetches 1-4 tiles depending on pixel position.
    """
    z = zoom or settings.point_elevation_default_zoom
    n = 2**z

    frac_x = _lng_to_tile_x_frac(lng, z)
    frac_y = _lat_to_tile_y_frac(lat, z)

    tile_x = int(math.floor(frac_x))
    tile_y = int(math.floor(frac_y))

    # Sub-tile pixel position (0-255 range within the tile)
    px = (frac_x - tile_x) * TILE_SIZE
    py = (frac_y - tile_y) * TILE_SIZE

    # Determine which tiles we need for bilinear neighbourhood
    # When px or py is near the edge, we need the adjacent tile
    need_right = px >= (TILE_SIZE - 1)
    need_bottom = py >= (TILE_SIZE - 1)

    tile_set: set[tuple[int, int, int]] = {(z, tile_x % n, max(0, min(tile_y, n - 1)))}
    if need_right:
        tile_set.add((z, (tile_x + 1) % n, max(0, min(tile_y, n - 1))))
    if need_bottom:
        tile_set.add((z, tile_x % n, max(0, min(tile_y + 1, n - 1))))
    if need_right and need_bottom:
        tile_set.add((z, (tile_x + 1) % n, max(0, min(tile_y + 1, n - 1))))

    # Fetch and decode all needed tiles (using cache)
    tile_data: dict[tuple[int, int], np.ndarray] = {}
    async with httpx.AsyncClient() as client:
        async def _fetch(tz: int, tx: int, ty: int) -> tuple[int, int, np.ndarray]:
            elev = await fetch_tile_decoded(client, tz, tx, ty)
            return tx, ty, elev

        results = await asyncio.gather(*(_fetch(tz, tx, ty) for tz, tx, ty in tile_set))
        for tx, ty, elev in results:
            tile_data[(tx, ty)] = elev

    # Bilinear interpolation
    # Integer pixel coordinates within the primary tile
    ix = min(int(math.floor(px)), TILE_SIZE - 1)
    iy = min(int(math.floor(py)), TILE_SIZE - 1)
    dx = px - ix
    dy = py - iy

    def _sample(pixel_x: int, pixel_y: int) -> float:
        """Get elevation at an absolute pixel position, crossing tile boundaries."""
        t_x = (tile_x + pixel_x // TILE_SIZE) % n
        t_y = max(0, min(tile_y + pixel_y // TILE_SIZE, n - 1))
        local_px = pixel_x % TILE_SIZE
        local_py = pixel_y % TILE_SIZE
        tile = tile_data.get((t_x, t_y))
        if tile is None:
            # Fallback: use primary tile edge
            tile = tile_data[(tile_x % n, max(0, min(tile_y, n - 1)))]
            local_px = min(local_px, TILE_SIZE - 1)
            local_py = min(local_py, TILE_SIZE - 1)
        return float(tile[local_py, local_px])

    e00 = _sample(ix, iy)
    e10 = _sample(ix + 1, iy)
    e01 = _sample(ix, iy + 1)
    e11 = _sample(ix + 1, iy + 1)

    elevation = (
        e00 * (1 - dx) * (1 - dy)
        + e10 * dx * (1 - dy)
        + e01 * (1 - dx) * dy
        + e11 * dx * dy
    )

    # Approximate meters per pixel at this zoom and latitude
    earth_circumference = 2 * math.pi * 6378137.0
    meters_per_pixel = (
        earth_circumference * math.cos(math.radians(lat)) / (n * TILE_SIZE)
    )

    return PointElevationResult(
        elevation_meters=round(elevation, 2),
        lat=lat,
        lng=lng,
        zoom=z,
        tile_coords=[(tz, tx, ty) for tz, tx, ty in tile_set],
        meters_per_pixel_approx=round(meters_per_pixel, 3),
    )


def build_fidelity_dict(snap: DEMSnapshot) -> dict:
    """Build the fidelity metadata dict from a DEMSnapshot."""
    return {
        "demProvider": settings.dem_provider,
        "zoomRequested": snap.zoom_requested,
        "zoomUsed": snap.zoom,
        "gridWidth": GRID_SIZE,
        "gridHeight": GRID_SIZE,
        "resampleMethod": "bilinear",
        "tileCount": len(snap.tile_coords),
    }


async def get_elevation_grid(
    lat: float, lng: float, radius_m: float, zoom: int | None = None
) -> dict:
    """Full pipeline: center+radius -> bounds -> tiles -> fetch -> decode -> resample -> stats."""
    snap = await fetch_dem_snapshot(lat, lng, radius_m, zoom)

    elevations = np.round(snap.dem, 1).tolist()

    return {
        "request": {
            "center": {"lat": lat, "lng": lng},
            "radiusMeters": radius_m,
            "zoomUsed": snap.zoom,
        },
        "bounds": {
            "north": round(snap.bounds.north, 6),
            "south": round(snap.bounds.south, 6),
            "east": round(snap.bounds.east, 6),
            "west": round(snap.bounds.west, 6),
        },
        "grid": {
            "width": GRID_SIZE,
            "height": GRID_SIZE,
            "cellSizeMetersApprox": snap.cell_size_meters,
            "elevations": elevations,
        },
        "tiles": [{"z": z, "x": x, "y": y} for z, x, y in snap.tile_coords],
        "stats": {
            "minElevation": round(float(np.min(snap.dem)), 1),
            "maxElevation": round(float(np.max(snap.dem)), 1),
            "meanElevation": round(float(np.mean(snap.dem)), 1),
        },
        "source": "aws-terrarium",
        "fidelity": build_fidelity_dict(snap),
    }
