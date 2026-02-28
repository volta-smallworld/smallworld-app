"""
Viewshed analysis via ray-casting on the DEM.

Core primitive reused by: visibility scoring, skyline extraction,
prospect-refuge computation, shadow casting, and mystery score.
"""

import numpy as np
from typing import Tuple
from log import get_logger

log = get_logger("scoring.viewshed")


def compute_viewshed(
    dem: np.ndarray,
    cam_row: int,
    cam_col: int,
    cam_z: float,
    res_m: float,
    max_distance_px: int = 300,
    n_rays: int = 360,
) -> np.ndarray:
    """Compute binary viewshed from a camera position.

    Cast rays radially outward. For each ray, track the maximum
    elevation angle seen so far. A cell is visible if its elevation
    angle exceeds all previous cells along that ray.

    Returns: (H, W) boolean mask, True = visible from camera.
    """
    h, w = dem.shape
    visible = np.zeros((h, w), dtype=bool)
    visible[cam_row, cam_col] = True

    log.debug(f"Computing viewshed at ({cam_row},{cam_col}), z={cam_z:.1f}m, "
              f"{n_rays} rays, max_dist={max_distance_px}px")

    for ray_idx in range(n_rays):
        angle = 2 * np.pi * ray_idx / n_rays
        dx = np.cos(angle)
        dy = np.sin(angle)

        max_elev_angle = -np.inf

        for step in range(1, max_distance_px):
            r = int(cam_row + dy * step)
            c = int(cam_col + dx * step)

            if not (0 <= r < h and 0 <= c < w):
                break

            # Distance in meters
            dist_m = step * res_m
            if dist_m < 1:
                continue

            # Elevation angle from camera to this cell
            dz = dem[r, c] - cam_z
            elev_angle = np.arctan2(dz, dist_m)

            if elev_angle >= max_elev_angle:
                visible[r, c] = True
                max_elev_angle = elev_angle

    log.debug(f"Viewshed complete: {visible.sum()} visible cells "
              f"({visible.sum() / visible.size * 100:.1f}%)")
    return visible


def compute_skyline(
    dem: np.ndarray,
    cam_row: int,
    cam_col: int,
    cam_z: float,
    res_m: float,
    fov_deg: float = 60.0,
    yaw_deg: float = 0.0,
    n_rays: int = 360,
    max_distance_px: int = 300,
) -> np.ndarray:
    """Compute skyline profile — max elevation angle per azimuth ray.

    The skyline IS the 1D profile of max elevation angles across
    the horizontal FOV. No rendering needed.

    Args:
        yaw_deg: center direction (0=N, 90=E)
        fov_deg: horizontal field of view

    Returns:
        1D array of elevation angles (radians), one per ray within FOV.
    """
    fov_rad = np.radians(fov_deg)
    yaw_rad = np.radians(yaw_deg)
    h, w = dem.shape

    # Rays spanning the FOV
    n_fov_rays = min(n_rays, int(fov_deg * 2))
    angles = np.linspace(
        yaw_rad - fov_rad / 2,
        yaw_rad + fov_rad / 2,
        n_fov_rays,
    )

    skyline = np.full(n_fov_rays, -np.pi / 2)

    for i, angle in enumerate(angles):
        dx = np.sin(angle)  # east component
        dy = -np.cos(angle)  # north component (row decreases = north)

        max_elev_angle = -np.inf

        for step in range(1, max_distance_px):
            r = int(cam_row + dy * step)
            c = int(cam_col + dx * step)

            if not (0 <= r < h and 0 <= c < w):
                break

            dist_m = step * res_m
            if dist_m < 1:
                continue

            dz = dem[r, c] - cam_z
            elev_angle = np.arctan2(dz, dist_m)

            if elev_angle > max_elev_angle:
                max_elev_angle = elev_angle

        skyline[i] = max_elev_angle

    return skyline


def compute_viewshed_area(
    viewshed: np.ndarray, res_m: float
) -> float:
    """Total visible area in square kilometers."""
    return viewshed.sum() * res_m**2 / 1e6


def compute_terrain_above_horizon(
    dem: np.ndarray,
    cam_row: int,
    cam_col: int,
    cam_z: float,
    res_m: float,
    max_distance_px: int = 100,
) -> float:
    """Compute solid angle of terrain above camera's horizon.

    Used for the "refuge" component of prospect-refuge scoring.
    Higher value = more enclosed/sheltered feeling.
    """
    h, w = dem.shape
    above_count = 0
    total_count = 0
    n_rays = 72  # coarser is fine for this

    for ray_idx in range(n_rays):
        angle = 2 * np.pi * ray_idx / n_rays
        dx = np.cos(angle)
        dy = np.sin(angle)

        # Check nearby terrain (within ~1-2km)
        for step in range(5, min(max_distance_px, 30)):
            r = int(cam_row + dy * step)
            c = int(cam_col + dx * step)

            if not (0 <= r < h and 0 <= c < w):
                break

            total_count += 1
            if dem[r, c] > cam_z:
                above_count += 1

    if total_count == 0:
        return 0.0
    return above_count / total_count
