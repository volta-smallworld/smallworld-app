"""
Fractal dimension computation for ridgeline profiles.

Compute viewing distance that produces a skyline with D ≈ 1.3
(the human aesthetic sweet spot per Sprott 2003, Hagerhall 2004).

This is pure DEM math — no rendering needed.
"""

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.interpolate import interp1d
from typing import List, Tuple, Optional
from dataclasses import dataclass
from config import TARGET_FRACTAL_DIM, DEFAULT_FOV_DEG
from log import get_logger

log = get_logger("camera.fractal")


@dataclass
class FractalCameraCandidate:
    """A camera position derived from fractal dimension analysis."""
    row: int
    col: int
    distance_m: float  # viewing distance from ridge
    fractal_dim: float  # actual D at this distance
    ridge_midpoint: Tuple[int, int]
    normal_direction: Tuple[float, float]  # unit vector perpendicular to ridge


def compute_fractal_distance(
    dem: np.ndarray,
    ridgeline_mask: np.ndarray,
    res_m: float,
    target_d: float = TARGET_FRACTAL_DIM,
    fov_deg: float = DEFAULT_FOV_DEG,
    image_width_px: int = 1920,
) -> List[FractalCameraCandidate]:
    """For each significant ridgeline, compute the viewing distance
    where the skyline fractal dimension ≈ target_d.

    Method:
    1. Extract individual ridgeline segments
    2. For each, compute elevation profile
    3. Compute FD at multiple smoothing scales
    4. Interpolate to find scale where D ≈ target_d
    5. Convert scale to viewing distance
    6. Place camera perpendicular to ridge at that distance
    """
    segments = _extract_ridge_segments(ridgeline_mask, dem, res_m)
    log.info(f"Computing fractal distance for {len(segments)} ridge segments, target D={target_d}")
    candidates = []

    for segment in segments:
        profile = _elevation_profile(segment, dem)
        if len(profile) < 20:
            continue

        result = _find_optimal_distance(
            profile, res_m, target_d, fov_deg, image_width_px
        )
        if result is None:
            continue

        optimal_distance, actual_fd = result

        # Ridge midpoint and normal
        mid_idx = len(segment) // 2
        mid_r, mid_c = segment[mid_idx]

        # Ridge direction at midpoint
        if mid_idx > 0 and mid_idx < len(segment) - 1:
            dr = segment[mid_idx + 1][0] - segment[mid_idx - 1][0]
            dc = segment[mid_idx + 1][1] - segment[mid_idx - 1][1]
        else:
            dr, dc = 0, 1

        # Normal = perpendicular to ridge direction
        length = np.sqrt(dr**2 + dc**2)
        if length < 0.1:
            continue
        normal = (-dc / length, dr / length)

        candidates.append(FractalCameraCandidate(
            row=mid_r, col=mid_c,
            distance_m=optimal_distance,
            fractal_dim=actual_fd,
            ridge_midpoint=(mid_r, mid_c),
            normal_direction=normal,
        ))

    log.info(f"Found {len(candidates)} fractal camera candidates"
             + (f", D range: {min(c.fractal_dim for c in candidates):.2f}-"
                f"{max(c.fractal_dim for c in candidates):.2f}"
                if candidates else ""))
    return candidates


def box_counting_fd(profile: np.ndarray) -> float:
    """Compute fractal dimension of a 1D profile via box counting.

    Overlay grids of decreasing box size, count boxes touching the profile.
    D = -slope of log(N) vs log(1/s).
    """
    n = len(profile)
    if n < 8:
        return 1.0

    # Normalize profile to 0-1
    pmin, pmax = profile.min(), profile.max()
    if pmax - pmin < 1e-10:
        return 1.0
    normalized = (profile - pmin) / (pmax - pmin)

    # Box sizes (powers of 2)
    sizes = []
    counts = []
    box_size = 2
    while box_size < n // 2:
        sizes.append(box_size)
        count = 0
        for i in range(0, n - box_size, box_size):
            segment = normalized[i:i + box_size]
            # Number of vertical boxes needed for this horizontal strip
            y_min = segment.min()
            y_max = segment.max()
            vertical_boxes = max(1, int(np.ceil((y_max - y_min) * n / box_size)))
            count += vertical_boxes
        counts.append(max(count, 1))
        box_size *= 2

    if len(sizes) < 2:
        return 1.0

    # Linear regression on log-log
    log_sizes = np.log(1.0 / np.array(sizes, dtype=float))
    log_counts = np.log(np.array(counts, dtype=float))

    # D = slope of log(N) vs log(1/s)
    coeffs = np.polyfit(log_sizes, log_counts, 1)
    return coeffs[0]


def _extract_ridge_segments(
    ridge_mask: np.ndarray, dem: np.ndarray, res_m: float,
    min_length_m: float = 1000,
) -> List[List[Tuple[int, int]]]:
    """Extract individual ridge segments as ordered point lists."""
    from scipy.ndimage import label
    labeled, n_features = label(ridge_mask)

    segments = []
    min_length_px = int(min_length_m / res_m)

    for i in range(1, min(n_features + 1, 50)):
        rows, cols = np.where(labeled == i)
        if len(rows) < min_length_px:
            continue

        # Order points along the ridge by traversal
        points = list(zip(rows.tolist(), cols.tolist()))
        ordered = _order_ridge_points(points)

        if len(ordered) >= min_length_px:
            segments.append(ordered)

    return segments


def _order_ridge_points(
    points: List[Tuple[int, int]]
) -> List[Tuple[int, int]]:
    """Order ridge points by nearest-neighbor traversal."""
    if len(points) <= 2:
        return points

    remaining = set(range(len(points)))
    ordered = [0]
    remaining.remove(0)

    while remaining:
        current = points[ordered[-1]]
        best_dist = float('inf')
        best_idx = -1
        for idx in remaining:
            p = points[idx]
            dist = (current[0] - p[0])**2 + (current[1] - p[1])**2
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        if best_dist > 25:  # gap too large, stop
            break
        ordered.append(best_idx)
        remaining.remove(best_idx)

    return [points[i] for i in ordered]


def _elevation_profile(
    segment: List[Tuple[int, int]], dem: np.ndarray
) -> np.ndarray:
    """Extract elevation values along a ridge segment."""
    return np.array([dem[r, c] for r, c in segment])


def _find_optimal_distance(
    profile: np.ndarray,
    res_m: float,
    target_d: float,
    fov_deg: float,
    image_width_px: int,
) -> Optional[Tuple[float, float]]:
    """Find viewing distance where profile FD ≈ target_d.

    Smooth the profile at multiple scales, compute FD at each,
    interpolate to find the scale producing target_d,
    convert scale to distance.
    """
    scales_m = [50, 100, 200, 500, 1000, 2000]
    fd_at_scale = {}

    for scale_m in scales_m:
        sigma_px = scale_m / res_m
        if sigma_px < 1:
            sigma_px = 1
        smoothed = gaussian_filter1d(profile, sigma=sigma_px)
        fd = box_counting_fd(smoothed)
        fd_at_scale[scale_m] = fd

    scales = sorted(fd_at_scale.keys())
    fds = [fd_at_scale[s] for s in scales]

    # Check if target_d falls within the range
    fd_min, fd_max = min(fds), max(fds)
    if target_d < fd_min or target_d > fd_max:
        # Use the scale closest to target
        best_scale = scales[np.argmin(np.abs(np.array(fds) - target_d))]
        best_fd = fd_at_scale[best_scale]
    else:
        # Interpolate to find exact scale
        try:
            interp = interp1d(fds, scales, kind='linear', fill_value='extrapolate')
            best_scale = float(interp(target_d))
            best_fd = target_d
        except Exception:
            best_scale = scales[np.argmin(np.abs(np.array(fds) - target_d))]
            best_fd = fd_at_scale[best_scale]

    # Convert scale to viewing distance
    # At distance d, pixel resolution ~ d * fov_rad / image_width
    fov_rad = np.radians(fov_deg)
    distance = best_scale * image_width_px / (len(profile) * fov_rad)
    distance = np.clip(distance, 200, 20000)

    return distance, best_fd
