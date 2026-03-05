"""Point context service — precise ground elevation plus optional local terrain analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from smallworld_api.config import settings
from smallworld_api.services.camera_geometry import bilinear_elevation
from smallworld_api.services.derivatives import (
    compute_local_relief,
    compute_profile_curvature,
    compute_slope_degrees,
)
from smallworld_api.services.terrarium import (
    fetch_dem_snapshot,
    sample_point_elevation,
)

logger = logging.getLogger(__name__)


@dataclass
class PointContextResult:
    ground_elevation_meters: float
    camera_agl_meters: float | None
    sampling: dict
    context: dict | None


async def get_point_context(
    lat: float,
    lng: float,
    camera_altitude_meters: float | None = None,
    context_radius_meters: float = 2000,
    zoom: int | None = None,
) -> PointContextResult:
    """Get precise ground elevation and optional local terrain context for a point.

    1. Uses raw-tile sampling for precise ground elevation (never 128x128 resampled).
    2. Optionally computes camera AGL if altitude is provided.
    3. Fetches a small-area DEM for local terrain derivatives.
    """
    # 1. Precise ground elevation
    point = await sample_point_elevation(lat, lng, zoom)
    ground_elev = point.elevation_meters

    # 2. Camera AGL
    camera_agl = None
    if camera_altitude_meters is not None:
        camera_agl = round(camera_altitude_meters - ground_elev, 2)

    sampling = {
        "zoom": point.zoom,
        "tiles_fetched": len(point.tile_coords),
        "meters_per_pixel_approx": point.meters_per_pixel_approx,
        "method": "bilinear_raw_tile",
    }

    # 3. Local DEM context
    context = None
    try:
        snap = await fetch_dem_snapshot(lat, lng, context_radius_meters, zoom)
        dem = snap.dem
        cell_size = snap.cell_size_meters

        slope = compute_slope_degrees(dem, cell_size)
        curvature = compute_profile_curvature(dem, cell_size)
        relief = compute_local_relief(dem)

        # Sample point-specific values from local DEM
        point_slope = bilinear_elevation(slope, snap.bounds, lat, lng)
        point_curvature = bilinear_elevation(curvature, snap.bounds, lat, lng)
        point_relief = bilinear_elevation(relief, snap.bounds, lat, lng)

        context = {
            "radius_meters": context_radius_meters,
            "cell_size_meters": cell_size,
            "elevation": {
                "min": round(float(np.min(dem)), 1),
                "max": round(float(np.max(dem)), 1),
                "mean": round(float(np.mean(dem)), 1),
            },
            "slope_degrees": {
                "at_point": round(float(point_slope), 2),
                "min": round(float(np.min(slope)), 1),
                "max": round(float(np.max(slope)), 1),
                "mean": round(float(np.mean(slope)), 1),
            },
            "curvature": {
                "at_point": round(float(point_curvature), 4),
                "min": round(float(np.min(curvature)), 4),
                "max": round(float(np.max(curvature)), 4),
                "mean": round(float(np.mean(curvature)), 4),
            },
            "local_relief_meters": {
                "at_point": round(float(point_relief), 1),
                "min": round(float(np.min(relief)), 1),
                "max": round(float(np.max(relief)), 1),
                "mean": round(float(np.mean(relief)), 1),
            },
        }
    except Exception:
        logger.warning("Failed to fetch local DEM context for (%s, %s)", lat, lng, exc_info=True)

    return PointContextResult(
        ground_elevation_meters=ground_elev,
        camera_agl_meters=camera_agl,
        sampling=sampling,
        context=context,
    )
