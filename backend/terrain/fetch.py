"""
DEM tile fetching from AWS Terrain Tiles (Mapzen Terrarium format).
Free, unlimited, no API key. Global coverage at ~30-75m resolution.

Terrarium encoding: elevation = (R * 256 + G + B / 256) - 32768
"""

import math
import numpy as np
import requests
from io import BytesIO
from PIL import Image
from typing import Tuple
from config import TERRAIN_TILE_URL, DEFAULT_ZOOM
from log import get_logger

log = get_logger("terrain.fetch")


def lat_lng_to_tile(lat: float, lng: float, zoom: int) -> Tuple[int, int]:
    """Convert lat/lng to tile coordinates at given zoom level."""
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y


def tile_to_lat_lng(x: int, y: int, zoom: int) -> Tuple[float, float]:
    """Convert tile coordinates back to lat/lng (top-left corner)."""
    n = 2 ** zoom
    lng = x / n * 360 - 180
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lng


def tile_resolution_meters(lat: float, zoom: int) -> float:
    """Approximate resolution in meters per pixel at given latitude and zoom."""
    return 156543.03 * math.cos(math.radians(lat)) / (2 ** zoom)


def decode_terrarium(img: np.ndarray) -> np.ndarray:
    """Decode Terrarium RGB to elevation in meters.

    Terrarium: elevation = (R * 256 + G + B / 256) - 32768
    Input: (H, W, 3) uint8 array
    Output: (H, W) float64 elevation in meters
    """
    r = img[:, :, 0].astype(np.float64)
    g = img[:, :, 1].astype(np.float64)
    b = img[:, :, 2].astype(np.float64)
    return (r * 256.0 + g + b / 256.0) - 32768.0


def fetch_tile(z: int, x: int, y: int) -> np.ndarray:
    """Fetch a single terrain tile and decode to elevation."""
    url = TERRAIN_TILE_URL.format(z=z, x=x, y=y)
    log.debug(f"Fetching tile z={z} x={x} y={y}")
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content))
    return decode_terrarium(np.array(img)[:, :, :3])


def fetch_dem(
    center_lat: float,
    center_lng: float,
    radius_km: float,
    zoom: int = DEFAULT_ZOOM,
) -> Tuple[np.ndarray, dict]:
    """
    Fetch a DEM grid covering the area around center_lat/center_lng.

    Returns:
        elevation: (H, W) float64 array of elevation in meters
        metadata: dict with bounds, resolution, origin, etc.
    """
    # Convert radius to approximate degree span
    lat_deg_per_km = 1 / 111.32
    lng_deg_per_km = 1 / (111.32 * math.cos(math.radians(center_lat)))

    lat_span = radius_km * lat_deg_per_km
    lng_span = radius_km * lng_deg_per_km

    # Bounding box
    lat_min = center_lat - lat_span
    lat_max = center_lat + lat_span
    lng_min = center_lng - lng_span
    lng_max = center_lng + lng_span

    # Find tile range
    x_min, y_max = lat_lng_to_tile(lat_min, lng_min, zoom)
    x_max, y_min = lat_lng_to_tile(lat_max, lng_max, zoom)

    # Ensure correct ordering
    if x_min > x_max:
        x_min, x_max = x_max, x_min
    if y_min > y_max:
        y_min, y_max = y_max, y_min

    # Fetch and stitch tiles
    tile_size = 256
    nx = x_max - x_min + 1
    ny = y_max - y_min + 1
    total_tiles = nx * ny

    log.info(f"Fetching {total_tiles} tiles ({nx}x{ny}) at zoom {zoom} "
             f"for {center_lat:.4f},{center_lng:.4f} r={radius_km}km")

    full_grid = np.zeros((ny * tile_size, nx * tile_size), dtype=np.float64)
    fetched = 0

    for ty in range(y_min, y_max + 1):
        for tx in range(x_min, x_max + 1):
            try:
                tile_elev = fetch_tile(zoom, tx, ty)
                row = (ty - y_min) * tile_size
                col = (tx - x_min) * tile_size
                full_grid[row:row + tile_size, col:col + tile_size] = tile_elev
                fetched += 1
            except Exception as e:
                log.warning(f"Failed to fetch tile z={zoom} x={tx} y={ty}: {e}")

    # Compute metadata
    top_lat, left_lng = tile_to_lat_lng(x_min, y_min, zoom)
    bot_lat, right_lng = tile_to_lat_lng(x_max + 1, y_max + 1, zoom)

    res_m = tile_resolution_meters(center_lat, zoom)

    log.info(f"Fetched {fetched}/{total_tiles} tiles → grid {full_grid.shape} "
             f"({res_m:.1f}m/px), elev range {full_grid.min():.0f}–{full_grid.max():.0f}m")

    metadata = {
        "bounds": {
            "lat_min": bot_lat,
            "lat_max": top_lat,
            "lng_min": left_lng,
            "lng_max": right_lng,
        },
        "center": {"lat": center_lat, "lng": center_lng},
        "radius_km": radius_km,
        "zoom": zoom,
        "resolution_m": res_m,
        "shape": full_grid.shape,
        "tile_range": {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max},
    }

    return full_grid, metadata


def pixel_to_lat_lng(row: int, col: int, metadata: dict) -> Tuple[float, float]:
    """Convert pixel coordinates in the DEM grid to lat/lng."""
    bounds = metadata["bounds"]
    h, w = metadata["shape"]
    lat = bounds["lat_max"] - (row / h) * (bounds["lat_max"] - bounds["lat_min"])
    lng = bounds["lng_min"] + (col / w) * (bounds["lng_max"] - bounds["lng_min"])
    return lat, lng


def lat_lng_to_pixel(lat: float, lng: float, metadata: dict) -> Tuple[int, int]:
    """Convert lat/lng to pixel coordinates in the DEM grid."""
    bounds = metadata["bounds"]
    h, w = metadata["shape"]
    row = int((bounds["lat_max"] - lat) / (bounds["lat_max"] - bounds["lat_min"]) * h)
    col = int((lng - bounds["lng_min"]) / (bounds["lng_max"] - bounds["lng_min"]) * w)
    return max(0, min(h - 1, row)), max(0, min(w - 1, col))
