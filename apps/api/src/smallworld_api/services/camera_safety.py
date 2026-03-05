"""Camera AGL (Above Ground Level) safety enforcement.

Two strategies:
- Precise: uses ``sample_point_elevation`` (network I/O, 1-4 raw tiles).
- DEM-based: uses ``bilinear_elevation`` on an already-loaded 128x128 grid (sync, no I/O).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from smallworld_api.config import settings
from smallworld_api.services.camera_geometry import bilinear_elevation
from smallworld_api.services.terrarium import sample_point_elevation
from smallworld_api.services.tiles import GeoBounds

logger = logging.getLogger(__name__)


@dataclass
class CameraSafetyResult:
    original_alt: float
    effective_alt: float
    ground_elev: float
    was_clamped: bool
    clearance: float


async def enforce_agl_floor_precise(
    lat: float,
    lng: float,
    alt: float,
    floor: float | None = None,
    zoom: int | None = None,
) -> CameraSafetyResult:
    """Enforce minimum AGL using precise tile sampling (async, network I/O)."""
    agl_floor = floor if floor is not None else settings.camera_agl_floor_meters
    point = await sample_point_elevation(lat, lng, zoom)
    ground = point.elevation_meters
    min_alt = ground + agl_floor
    clamped = alt < min_alt
    effective = max(alt, min_alt)
    return CameraSafetyResult(
        original_alt=alt,
        effective_alt=round(effective, 2),
        ground_elev=ground,
        was_clamped=clamped,
        clearance=round(effective - ground, 2),
    )


def enforce_agl_floor_dem(
    lat: float,
    lng: float,
    alt: float,
    dem: NDArray[np.floating],
    bounds: GeoBounds,
    floor: float | None = None,
) -> CameraSafetyResult:
    """Enforce minimum AGL using an already-loaded DEM grid (sync, no I/O)."""
    agl_floor = floor if floor is not None else settings.camera_agl_floor_meters
    ground = bilinear_elevation(dem, bounds, lat, lng)
    min_alt = ground + agl_floor
    clamped = alt < min_alt
    effective = max(alt, min_alt)
    return CameraSafetyResult(
        original_alt=alt,
        effective_alt=round(effective, 2),
        ground_elev=round(ground, 2),
        was_clamped=clamped,
        clearance=round(effective - ground, 2),
    )
