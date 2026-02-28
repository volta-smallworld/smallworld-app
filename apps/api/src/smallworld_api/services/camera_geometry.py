"""Geometry primitives for the viewpoint camera solver.

Works with a 128x128 DEM grid (numpy ndarray of elevations in meters)
and GeoBounds from smallworld_api.services.tiles.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from smallworld_api.services.tiles import GeoBounds

EARTH_RADIUS = 6378137.0


# ---------------------------------------------------------------------------
# Coordinate transforms
# ---------------------------------------------------------------------------


def latlng_to_enu(
    lat: float, lng: float, origin_lat: float, origin_lng: float
) -> tuple[float, float]:
    """Convert lat/lng to local East-North-Up metres relative to an origin."""
    origin_lat_rad = math.radians(origin_lat)
    east = (lng - origin_lng) * math.cos(origin_lat_rad) * EARTH_RADIUS * math.pi / 180
    north = (lat - origin_lat) * EARTH_RADIUS * math.pi / 180
    return (east, north)


def enu_to_latlng(
    east: float, north: float, origin_lat: float, origin_lng: float
) -> tuple[float, float]:
    """Inverse of latlng_to_enu — convert ENU metres back to lat/lng."""
    origin_lat_rad = math.radians(origin_lat)
    lat = origin_lat + math.degrees(north / EARTH_RADIUS)
    lng = origin_lng + math.degrees(east / (EARTH_RADIUS * math.cos(origin_lat_rad)))
    return (lat, lng)


# ---------------------------------------------------------------------------
# DEM sampling
# ---------------------------------------------------------------------------


def bilinear_elevation(
    dem: NDArray[np.floating], bounds: GeoBounds, lat: float, lng: float
) -> float:
    """Sample elevation from a DEM grid using bilinear interpolation."""
    h, w = dem.shape[:2]

    # Convert lat/lng to fractional row/col.
    row = (bounds.north - lat) / (bounds.north - bounds.south) * (h - 1)
    col = (lng - bounds.west) / (bounds.east - bounds.west) * (w - 1)

    # Clamp to grid bounds.
    row = max(0.0, min(row, h - 1.0))
    col = max(0.0, min(col, w - 1.0))

    r0 = int(math.floor(row))
    c0 = int(math.floor(col))
    r1 = min(r0 + 1, h - 1)
    c1 = min(c0 + 1, w - 1)

    dr = row - r0
    dc = col - c0

    # Bilinear interpolation.
    top = dem[r0, c0] * (1 - dc) + dem[r0, c1] * dc
    bot = dem[r1, c0] * (1 - dc) + dem[r1, c1] * dc
    return float(top * (1 - dr) + bot * dr)


# ---------------------------------------------------------------------------
# Heading / pitch helpers
# ---------------------------------------------------------------------------


def compute_heading(
    from_east: float, from_north: float, to_east: float, to_north: float
) -> float:
    """Compute heading in degrees [0, 360) from one ENU point to another."""
    heading = math.degrees(
        math.atan2(to_east - from_east, to_north - from_north)
    )
    return heading % 360


def pitch_from_horizon_ratio(horizon_ratio: float, fov_degrees: float) -> float:
    """Compute pitch angle from a desired horizon position in the frame.

    *horizon_ratio* is the vertical fraction (0 = top, 1 = bottom) where the
    horizon should appear.  *fov_degrees* is the horizontal FOV; vertical FOV
    is derived assuming 16:9 aspect.

    Returns pitch in degrees (negative means looking down).
    """
    vertical_fov = fov_degrees * (9 / 16)
    vertical_fov_rad = math.radians(vertical_fov)
    pitch_rad = math.atan((horizon_ratio - 0.5) * 2 * math.tan(vertical_fov_rad / 2))
    return math.degrees(pitch_rad)


# ---------------------------------------------------------------------------
# Pinhole projection
# ---------------------------------------------------------------------------


def project_to_image(
    point_enu: tuple[float, float, float],
    cam_enu: tuple[float, float],
    cam_alt: float,
    heading_deg: float,
    pitch_deg: float,
    fov_deg: float,
) -> tuple[float, float] | None:
    """Project a 3D ENU point to normalised image coordinates (pinhole model).

    Returns ``(xNorm, yNorm)`` in [0, 1]x[0, 1] or ``None`` if the point is
    behind the camera or outside the frame.
    """
    heading_rad = math.radians(heading_deg)
    pitch_rad = math.radians(pitch_deg)

    # Forward direction vector (un-normalised).
    fx = math.sin(heading_rad)
    fy = math.cos(heading_rad)
    fz = math.sin(pitch_rad)
    flen = math.sqrt(fx * fx + fy * fy + fz * fz)
    fx /= flen
    fy /= flen
    fz /= flen

    # Right = forward x world_up,  where world_up = (0, 0, 1).
    rx = fy * 1 - fz * 0  # fy
    ry = fz * 0 - fx * 1  # -fx
    rz = fx * 0 - fy * 0  # 0
    rlen = math.sqrt(rx * rx + ry * ry + rz * rz)
    rx /= rlen
    ry /= rlen
    rz /= rlen

    # Up = right x forward.
    ux = ry * fz - rz * fy
    uy = rz * fx - rx * fz
    uz = rx * fy - ry * fx

    # Delta from camera to point.
    dx = point_enu[0] - cam_enu[0]
    dy = point_enu[1] - cam_enu[1]
    dz = point_enu[2] - cam_alt

    # Camera-local coordinates.
    cam_x = dx * rx + dy * ry + dz * rz
    cam_y = dx * ux + dy * uy + dz * uz
    cam_z = dx * fx + dy * fy + dz * fz

    if cam_z <= 0:
        return None

    hfov_rad = math.radians(fov_deg)
    vfov_rad = math.radians(fov_deg * 9 / 16)

    x_norm = 0.5 + (cam_x / cam_z) / (2 * math.tan(hfov_rad / 2))
    y_norm = 0.5 - (cam_y / cam_z) / (2 * math.tan(vfov_rad / 2))

    if not (0 <= x_norm <= 1 and 0 <= y_norm <= 1):
        return None

    return (x_norm, y_norm)


# ---------------------------------------------------------------------------
# Line-of-sight
# ---------------------------------------------------------------------------


def check_line_of_sight(
    dem: NDArray[np.floating],
    bounds: GeoBounds,
    cam_lat: float,
    cam_lng: float,
    cam_alt: float,
    target_lat: float,
    target_lng: float,
    target_alt: float,
    num_samples: int = 64,
    clearance: float = 0.5,
) -> bool:
    """Check line-of-sight between camera and target via DEM ray marching.

    Returns ``True`` if the sight-line is clear, ``False`` if terrain blocks it.
    The first and last two samples are excluded from the occlusion test to avoid
    self-intersection at the endpoints.
    """
    for i in range(num_samples):
        t = i / (num_samples - 1)

        # Skip the first and last 2 samples.
        if i < 2 or i >= num_samples - 2:
            continue

        sample_lat = cam_lat + t * (target_lat - cam_lat)
        sample_lng = cam_lng + t * (target_lng - cam_lng)
        ray_alt = cam_alt + t * (target_alt - cam_alt)

        terrain_elev = bilinear_elevation(dem, bounds, sample_lat, sample_lng)

        if terrain_elev > ray_alt - clearance:
            return False

    return True
