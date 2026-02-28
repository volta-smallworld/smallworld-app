"""Fractal-dimension utilities for ridge analysis and preferred viewing distance."""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage


# ── Box-counting fractal dimension ──────────────────────────────────────────


def box_counting_fd(profile: np.ndarray) -> float:
    """Compute the 1D box-counting fractal dimension of a 1D elevation profile.

    Normalizes the profile to [0, 1], then counts boxes at powers-of-2 scales.
    Returns the slope of log(count) vs log(1/size), which estimates the fractal
    dimension.  Returns 1.0 for profiles shorter than 4 samples.
    """
    n = len(profile)
    if n < 4:
        return 1.0

    # Normalize to [0, 1]
    mn, mx = float(profile.min()), float(profile.max())
    if mx - mn < 1e-12:
        return 1.0
    normed = (profile - mn) / (mx - mn)

    sizes: list[int] = []
    counts: list[int] = []

    # Box sizes: powers of 2 from 2 up to n // 2
    s = 2
    while s <= n // 2:
        box_size = s / n  # normalized box width/height
        total_boxes = 0
        # Divide x-axis into segments of width s
        for i in range(0, n, s):
            segment = normed[i : min(i + s, n)]
            if len(segment) == 0:
                continue
            y_min = float(segment.min())
            y_max = float(segment.max())
            # Count how many boxes of height box_size cover the y range
            j_min = int(math.floor(y_min / box_size))
            j_max = int(math.floor(y_max / box_size))
            total_boxes += j_max - j_min + 1
        if total_boxes > 0:
            sizes.append(s)
            counts.append(total_boxes)
        s *= 2

    if len(sizes) < 2:
        return 1.0

    # Fit log(count) vs log(1/size)
    log_inv_size = np.array([math.log(n / s) for s in sizes])
    log_count = np.array([math.log(c) for c in counts])
    coeffs = np.polyfit(log_inv_size, log_count, 1)
    return float(coeffs[0])


# ── Fractal score ───────────────────────────────────────────────────────────


def fractal_score(fd: float, target: float = 1.3, sigma: float = 0.15) -> float:
    """Gaussian score centered at target FD, returning a value in [0, 1]."""
    return math.exp(-((fd - target) ** 2) / (2 * sigma**2))


# ── Profile smoothing ──────────────────────────────────────────────────────


def smooth_profile(elevations: np.ndarray, scale_cells: int) -> np.ndarray:
    """Smooth a 1D elevation profile using a Gaussian filter.

    Sigma is set to scale_cells / 3 so the kernel spans roughly one scale width.
    """
    sigma = scale_cells / 3.0
    return ndimage.gaussian_filter1d(elevations, sigma=sigma)


# ── Ridge profile sampling ─────────────────────────────────────────────────


def ridge_profile_from_path(
    path: list[dict],
    dem: np.ndarray,
    bounds,
    num_samples: int = 64,
) -> np.ndarray:
    """Sample elevation values along a ridge path from the DEM.

    Points are evenly spaced along the path using nearest-neighbor lookup in the
    DEM grid.  *bounds* is expected to expose .north, .south, .east, .west
    (duck-typed GeoBounds).
    """
    h, w = dem.shape

    if len(path) < 2:
        # Single point — just sample it
        if len(path) == 1:
            lat, lng = path[0]["lat"], path[0]["lng"]
            row = int(round((bounds.north - lat) / (bounds.north - bounds.south) * (h - 1)))
            col = int(round((lng - bounds.west) / (bounds.east - bounds.west) * (w - 1)))
            row = max(0, min(h - 1, row))
            col = max(0, min(w - 1, col))
            return np.array([float(dem[row, col])] * num_samples)
        return np.zeros(num_samples)

    # Compute cumulative arc length along the path
    arc_lengths = [0.0]
    for i in range(1, len(path)):
        dlat = path[i]["lat"] - path[i - 1]["lat"]
        dlng = path[i]["lng"] - path[i - 1]["lng"]
        arc_lengths.append(arc_lengths[-1] + math.sqrt(dlat**2 + dlng**2))

    total_length = arc_lengths[-1]
    if total_length < 1e-12:
        # All points coincide
        lat, lng = path[0]["lat"], path[0]["lng"]
        row = int(round((bounds.north - lat) / (bounds.north - bounds.south) * (h - 1)))
        col = int(round((lng - bounds.west) / (bounds.east - bounds.west) * (w - 1)))
        row = max(0, min(h - 1, row))
        col = max(0, min(w - 1, col))
        return np.array([float(dem[row, col])] * num_samples)

    # Sample num_samples evenly spaced points along the arc
    sample_distances = np.linspace(0, total_length, num_samples)
    elevations = np.empty(num_samples, dtype=np.float64)
    seg_idx = 0

    for si, d in enumerate(sample_distances):
        # Advance to the correct segment
        while seg_idx < len(arc_lengths) - 2 and arc_lengths[seg_idx + 1] < d:
            seg_idx += 1

        # Interpolate lat/lng along the segment
        seg_start = arc_lengths[seg_idx]
        seg_end = arc_lengths[seg_idx + 1] if seg_idx + 1 < len(arc_lengths) else seg_start
        seg_len = seg_end - seg_start
        if seg_len < 1e-12:
            t = 0.0
        else:
            t = (d - seg_start) / seg_len

        lat = path[seg_idx]["lat"] + t * (path[min(seg_idx + 1, len(path) - 1)]["lat"] - path[seg_idx]["lat"])
        lng = path[seg_idx]["lng"] + t * (path[min(seg_idx + 1, len(path) - 1)]["lng"] - path[seg_idx]["lng"])

        # Map to grid coordinates (nearest-neighbor)
        row = int(round((bounds.north - lat) / (bounds.north - bounds.south) * (h - 1)))
        col = int(round((lng - bounds.west) / (bounds.east - bounds.west) * (w - 1)))
        row = max(0, min(h - 1, row))
        col = max(0, min(w - 1, col))
        elevations[si] = float(dem[row, col])

    return elevations


# ── Preferred viewing distance ──────────────────────────────────────────────

_DEFAULT_SCALES_METERS = [150, 300, 600, 1200]
_MIN_DISTANCE = 400.0
_MAX_DISTANCE = 15000.0


def preferred_viewing_distance(
    path: list[dict],
    dem: np.ndarray,
    bounds,
    cell_size_meters: float,
    fov_degrees: float = 55,
    target_fd: float = 1.3,
    scales_meters: list[float] | None = None,
) -> float:
    """Compute preferred viewing distance using ridge fractal dimension.

    Samples the ridge profile, smooths it at multiple scales, and selects the
    scale whose fractal dimension is closest to *target_fd*.  The viewing
    distance is then derived from the chosen scale and the camera field of view.
    """
    if scales_meters is None:
        scales_meters = _DEFAULT_SCALES_METERS

    profile = ridge_profile_from_path(path, dem, bounds)

    best_scale_m = scales_meters[0]
    best_fd_diff = float("inf")

    for scale_m in scales_meters:
        scale_cells = max(1, int(scale_m / cell_size_meters))
        smoothed = smooth_profile(profile, scale_cells)
        fd = box_counting_fd(smoothed)
        fd_diff = abs(fd - target_fd)
        if fd_diff < best_fd_diff:
            best_fd_diff = fd_diff
            best_scale_m = scale_m

    fov_radians = math.radians(fov_degrees)
    distance = best_scale_m / math.tan(fov_radians / 2)

    return max(_MIN_DISTANCE, min(_MAX_DISTANCE, distance))


# ── Fallback viewing distance ──────────────────────────────────────────────


def fallback_viewing_distance(
    scene_extent_meters: float,
    multiplier: float = 2.5,
) -> float:
    """Compute a default viewing distance when no ridge is available."""
    distance = max(scene_extent_meters * multiplier, _MIN_DISTANCE)
    return min(distance, _MAX_DISTANCE)
