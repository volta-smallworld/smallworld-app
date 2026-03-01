import asyncio
import io
import math
from dataclasses import dataclass

import httpx
import numpy as np
from PIL import Image

from smallworld_api.config import settings
from smallworld_api.services.tiles import (
    GeoBounds,
    TileRange,
    bounds_to_tile_range,
    center_radius_to_bounds,
    tile_bounds,
)

TILE_SIZE = 256
GRID_SIZE = 128
TILE_FETCH_CONCURRENCY = 8


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


async def fetch_and_stitch(
    client: httpx.AsyncClient, tile_range: TileRange
) -> tuple[np.ndarray, GeoBounds]:
    """Fetch all tiles in a range, decode, and stitch into a single elevation array.

    Returns the stitched elevation array and the geographic bounds of the mosaic.
    """
    cols = tile_range.x_max - tile_range.x_min + 1
    rows = tile_range.y_max - tile_range.y_min + 1
    mosaic = np.zeros((rows * TILE_SIZE, cols * TILE_SIZE), dtype=np.float64)

    tile_coords = tile_range.tile_coords()
    semaphore = asyncio.Semaphore(TILE_FETCH_CONCURRENCY)

    async def _fetch_decode(z: int, x: int, y: int) -> tuple[int, int, int, np.ndarray]:
        async with semaphore:
            img = await fetch_tile(client, z, x, y)
        return z, x, y, decode_terrarium(img)

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
    """Crop the mosaic to target bounds and resample to a fixed grid size."""
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

    # Resample to grid_size x grid_size using simple nearest-neighbor via numpy
    row_indices = np.linspace(0, cropped.shape[0] - 1, grid_size).astype(int)
    col_indices = np.linspace(0, cropped.shape[1] - 1, grid_size).astype(int)
    return cropped[np.ix_(row_indices, col_indices)]


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


def _resolve_tile_range(
    target_bounds: GeoBounds,
    zoom: int | None = None,
) -> TileRange:
    """Choose the highest zoom that stays within the server tile cap."""
    requested_zoom = zoom or settings.default_terrarium_zoom

    for candidate_zoom in range(requested_zoom, -1, -1):
        tile_range = bounds_to_tile_range(target_bounds, candidate_zoom)
        if tile_range.tile_count <= settings.max_tiles_per_request:
            return tile_range

    raise ValueError(
        f"Request covers more than {settings.max_tiles_per_request} tiles even at the lowest supported zoom. "
        f"Try a smaller radius."
    )


async def fetch_dem_snapshot(
    lat: float, lng: float, radius_m: float, zoom: int | None = None
) -> DEMSnapshot:
    """Fetch tiles, decode, stitch, crop, and resample into a 128x128 DEM grid."""
    target_bounds = center_radius_to_bounds(lat, lng, radius_m)
    tile_range = _resolve_tile_range(target_bounds, zoom)

    async with httpx.AsyncClient() as client:
        mosaic, mosaic_bounds = await fetch_and_stitch(client, tile_range)

    grid = crop_and_resample(mosaic, mosaic_bounds, target_bounds, GRID_SIZE)

    return DEMSnapshot(
        dem=grid,
        bounds=target_bounds,
        tile_coords=tile_range.tile_coords(),
        zoom=tile_range.z,
        cell_size_meters=compute_cell_size_meters(target_bounds, GRID_SIZE),
    )


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
    }
