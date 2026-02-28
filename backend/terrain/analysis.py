"""
Terrain derivative computation: slope, curvature, Laplacian.
All computed from the DEM using standard geomorphometry kernels.
"""

import numpy as np
from scipy.ndimage import uniform_filter, generic_filter
from log import get_logger

log = get_logger("terrain.analysis")


def compute_derivatives(dem: np.ndarray, res_m: float) -> dict:
    """Compute all terrain derivatives from a DEM.

    Args:
        dem: (H, W) elevation array in meters
        res_m: pixel resolution in meters

    Returns:
        dict with slope, aspect, profile_curvature, plan_curvature,
        laplacian, gaussian_curvature
    """
    log.info(f"Computing derivatives for DEM {dem.shape}, res={res_m:.1f}m")

    slope, aspect, dz_dx, dz_dy = compute_slope(dem, res_m)
    log.debug(f"Slope range: {slope.min():.1f}-{slope.max():.1f} deg")

    profile_curv, plan_curv = compute_curvature(dem, res_m, dz_dx, dz_dy)
    laplacian = compute_laplacian(dem, res_m)
    gauss_curv = compute_gaussian_curvature(dem, res_m)

    log.info(f"Derivatives computed: slope mean={slope.mean():.1f} deg, "
             f"max curvature={np.abs(profile_curv).max():.4f}")

    return {
        "slope": slope,
        "aspect": aspect,
        "profile_curvature": profile_curv,
        "plan_curvature": plan_curv,
        "laplacian": laplacian,
        "gaussian_curvature": gauss_curv,
        "dz_dx": dz_dx,
        "dz_dy": dz_dy,
    }


def compute_slope(
    dem: np.ndarray, res_m: float
) -> tuple:
    """Compute slope and aspect using Horn's formula (3x3 kernel).

    Horn's formula uses a weighted average of finite differences
    over a 3x3 neighborhood for robust gradient estimation.

    Returns: (slope_deg, aspect_deg, dz_dx, dz_dy)
    """
    # Pad edges to handle boundaries
    padded = np.pad(dem, 1, mode="edge")

    # Horn's 3x3 weighted differences
    # dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8 * res)
    # dz/dy = ((g + 2h + i) - (a + 2b + c)) / (8 * res)
    a = padded[:-2, :-2]
    b = padded[:-2, 1:-1]
    c = padded[:-2, 2:]
    d = padded[1:-1, :-2]
    # e = padded[1:-1, 1:-1]  # center, unused
    f = padded[1:-1, 2:]
    g = padded[2:, :-2]
    h = padded[2:, 1:-1]
    i = padded[2:, 2:]

    dz_dx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * res_m)
    dz_dy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * res_m)

    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad)
    aspect_rad = np.arctan2(-dz_dy, dz_dx)
    aspect_deg = np.degrees(aspect_rad) % 360

    return slope_deg, aspect_deg, dz_dx, dz_dy


def compute_curvature(
    dem: np.ndarray, res_m: float,
    dz_dx: np.ndarray = None, dz_dy: np.ndarray = None
) -> tuple:
    """Compute profile and plan curvature.

    Profile curvature: curvature in the direction of steepest slope.
    Positive = convex (cliff top), negative = concave (valley bottom).

    Plan curvature: curvature perpendicular to slope.
    Positive = ridge, negative = valley.

    Returns: (profile_curvature, plan_curvature)
    """
    if dz_dx is None or dz_dy is None:
        _, _, dz_dx, dz_dy = compute_slope(dem, res_m)

    # Second derivatives via central differences
    padded = np.pad(dem, 1, mode="edge")
    center = padded[1:-1, 1:-1]

    dz_dxx = (padded[1:-1, 2:] - 2 * center + padded[1:-1, :-2]) / (res_m**2)
    dz_dyy = (padded[2:, 1:-1] - 2 * center + padded[:-2, 1:-1]) / (res_m**2)
    dz_dxy = (
        padded[2:, 2:] - padded[2:, :-2] - padded[:-2, 2:] + padded[:-2, :-2]
    ) / (4 * res_m**2)

    p = dz_dx**2
    q = dz_dy**2
    pq = p + q

    # Avoid division by zero on flat terrain
    denom = pq * np.sqrt(1 + pq)
    denom = np.where(denom < 1e-10, 1e-10, denom)

    # Profile curvature (along slope direction)
    profile_curv = -(
        p * dz_dxx + 2 * dz_dx * dz_dy * dz_dxy + q * dz_dyy
    ) / denom

    # Plan curvature (across slope direction)
    denom2 = np.power(1 + pq, 1.5)
    denom2 = np.where(denom2 < 1e-10, 1e-10, denom2)

    plan_curv = -(
        q * dz_dxx - 2 * dz_dx * dz_dy * dz_dxy + p * dz_dyy
    ) / denom2

    return profile_curv, plan_curv


def compute_laplacian(dem: np.ndarray, res_m: float) -> np.ndarray:
    """Laplacian (sum of second partial derivatives). Highlights dramatic terrain changes."""
    padded = np.pad(dem, 1, mode="edge")
    center = padded[1:-1, 1:-1]
    lap = (
        padded[1:-1, 2:] + padded[1:-1, :-2] +
        padded[2:, 1:-1] + padded[:-2, 1:-1] -
        4 * center
    ) / (res_m**2)
    return lap


def compute_gaussian_curvature(dem: np.ndarray, res_m: float) -> np.ndarray:
    """Gaussian curvature = product of principal curvatures.
    Strongly negative → saddle point (passes).
    Strongly positive → dome or bowl."""
    padded = np.pad(dem, 1, mode="edge")
    center = padded[1:-1, 1:-1]

    dz_dxx = (padded[1:-1, 2:] - 2 * center + padded[1:-1, :-2]) / (res_m**2)
    dz_dyy = (padded[2:, 1:-1] - 2 * center + padded[:-2, 1:-1]) / (res_m**2)
    dz_dxy = (
        padded[2:, 2:] - padded[2:, :-2] - padded[:-2, 2:] + padded[:-2, :-2]
    ) / (4 * res_m**2)

    return dz_dxx * dz_dyy - dz_dxy**2


def local_elevation_range(dem: np.ndarray, window: int = 21) -> np.ndarray:
    """Local relief: difference between max and min elevation in a window."""
    from scipy.ndimage import maximum_filter, minimum_filter
    local_max = maximum_filter(dem, size=window)
    local_min = minimum_filter(dem, size=window)
    return local_max - local_min
