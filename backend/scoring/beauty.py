"""
Beauty scoring: all non-compositional beauty factors.
Computed entirely from DEM data — no rendering needed.

Factors: viewshed richness, viewpoint entropy, skyline fractal dimension,
prospect-refuge, depth layering, mystery score, water visibility.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional
from .viewshed import (
    compute_viewshed, compute_skyline, compute_viewshed_area,
    compute_terrain_above_horizon,
)
from camera.fractal import box_counting_fd
from config import (
    DEFAULT_BEAUTY_WEIGHTS, TARGET_FRACTAL_DIM, FRACTAL_DIM_SIGMA,
)
from log import get_logger

log = get_logger("scoring.beauty")


@dataclass
class BeautyScores:
    """All beauty scores for a single viewpoint."""
    viewshed_richness: float = 0.0
    viewpoint_entropy: float = 0.0
    skyline_fractal: float = 0.0
    prospect_refuge: float = 0.0
    depth_layering: float = 0.0
    mystery: float = 0.0
    water_visibility: float = 0.0
    total: float = 0.0

    def to_dict(self):
        return {
            "viewshed_richness": round(self.viewshed_richness, 3),
            "viewpoint_entropy": round(self.viewpoint_entropy, 3),
            "skyline_fractal": round(self.skyline_fractal, 3),
            "prospect_refuge": round(self.prospect_refuge, 3),
            "depth_layering": round(self.depth_layering, 3),
            "mystery": round(self.mystery, 3),
            "water_visibility": round(self.water_visibility, 3),
            "total": round(self.total, 3),
        }


def score_beauty(
    dem: np.ndarray,
    cam_row: int,
    cam_col: int,
    cam_z: float,
    res_m: float,
    interest_map: np.ndarray,
    water_mask: np.ndarray,
    fov_deg: float = 60.0,
    yaw_deg: float = 0.0,
    weights: dict = None,
) -> BeautyScores:
    """Compute all beauty scores for a camera position."""
    w = {**DEFAULT_BEAUTY_WEIGHTS, **(weights or {})}

    log.debug(f"Scoring beauty at ({cam_row},{cam_col}), z={cam_z:.1f}m, "
              f"fov={fov_deg} yaw={yaw_deg:.1f}")

    # Viewshed (reused by multiple scorers)
    viewshed = compute_viewshed(dem, cam_row, cam_col, cam_z, res_m)

    scores = BeautyScores()

    # 1. Viewshed richness: visible area weighted by interest
    scores.viewshed_richness = _viewshed_richness(viewshed, interest_map)

    # 2. Viewpoint entropy
    scores.viewpoint_entropy = _viewpoint_entropy(dem, viewshed)

    # 3. Skyline fractal dimension
    skyline = compute_skyline(dem, cam_row, cam_col, cam_z, res_m, fov_deg, yaw_deg)
    scores.skyline_fractal = _skyline_fractal_score(skyline)

    # 4. Prospect-refuge
    scores.prospect_refuge = _prospect_refuge(
        dem, cam_row, cam_col, cam_z, res_m, viewshed
    )

    # 5. Depth layering
    scores.depth_layering = _depth_layering(
        dem, cam_row, cam_col, res_m, viewshed
    )

    # 6. Mystery score
    scores.mystery = _mystery_score(
        dem, cam_row, cam_col, cam_z, res_m, viewshed, interest_map
    )

    # 7. Water visibility
    scores.water_visibility = _water_visibility(viewshed, water_mask)

    # Weighted total
    scores.total = (
        w["viewshed_richness"] * scores.viewshed_richness +
        w["viewpoint_entropy"] * scores.viewpoint_entropy +
        w["skyline_fractal"] * scores.skyline_fractal +
        w["prospect_refuge"] * scores.prospect_refuge +
        w["depth_layering"] * scores.depth_layering +
        w["mystery"] * scores.mystery +
        w["water_visibility"] * scores.water_visibility
    )

    log.debug(f"Beauty scores: total={scores.total:.3f} "
              f"(richness={scores.viewshed_richness:.2f}, "
              f"fractal={scores.skyline_fractal:.2f}, "
              f"prospect={scores.prospect_refuge:.2f})")
    return scores


def _viewshed_richness(viewshed: np.ndarray, interest_map: np.ndarray) -> float:
    """How much interesting terrain is visible."""
    visible_interest = interest_map[viewshed].sum()
    max_possible = interest_map.sum()
    if max_possible < 1e-10:
        return 0.0
    return min(1.0, visible_interest / (max_possible * 0.3))  # 30% visible = perfect


def _viewpoint_entropy(dem: np.ndarray, viewshed: np.ndarray) -> float:
    """Shannon entropy of elevation distribution in visible area.
    Diverse terrain = high entropy = interesting view.
    """
    visible_elevs = dem[viewshed]
    if len(visible_elevs) < 10:
        return 0.0

    # Bin into 20 elevation bins
    n_bins = 20
    hist, _ = np.histogram(visible_elevs, bins=n_bins)
    hist = hist[hist > 0]  # remove empty bins

    # Normalize to probabilities
    probs = hist / hist.sum()

    # Shannon entropy
    entropy = -np.sum(probs * np.log2(probs))

    # Normalize to 0-1 (max entropy = log2(n_bins))
    max_entropy = np.log2(n_bins)
    return min(1.0, entropy / max_entropy)


def _skyline_fractal_score(skyline: np.ndarray) -> float:
    """Score skyline by how close its fractal dimension is to 1.3.
    Gaussian kernel centered at TARGET_FRACTAL_DIM.
    """
    if len(skyline) < 10:
        return 0.0

    fd = box_counting_fd(skyline)

    # Gaussian score peaked at target
    score = np.exp(-0.5 * ((fd - TARGET_FRACTAL_DIM) / FRACTAL_DIM_SIGMA) ** 2)
    return score


def _prospect_refuge(
    dem: np.ndarray,
    cam_row: int, cam_col: int, cam_z: float,
    res_m: float,
    viewshed: np.ndarray,
) -> float:
    """Prospect-refuge balance (Appleton 1975).

    Prospect = viewshed area (can see far).
    Refuge = terrain above horizon nearby (feeling of shelter).
    Score = harmonic mean — rewards balanced views.
    """
    # Prospect: normalized viewshed area
    area_km2 = compute_viewshed_area(viewshed, res_m)
    prospect = min(1.0, area_km2 / 50.0)  # 50 km² = fully open

    # Refuge: fraction of nearby terrain above camera
    refuge = compute_terrain_above_horizon(dem, cam_row, cam_col, cam_z, res_m)

    # Harmonic mean: rewards balance, penalizes extremes
    if prospect + refuge < 1e-10:
        return 0.0
    return 2 * prospect * refuge / (prospect + refuge)


def _depth_layering(
    dem: np.ndarray,
    cam_row: int, cam_col: int,
    res_m: float,
    viewshed: np.ndarray,
) -> float:
    """Score evenness of foreground/midground/background distribution.

    Bin visible terrain into 3 distance zones.
    Even distribution = good depth = higher score.
    """
    h, w = dem.shape
    visible_rows, visible_cols = np.where(viewshed)

    if len(visible_rows) < 10:
        return 0.0

    # Distance from camera to each visible cell
    distances = np.sqrt(
        ((visible_rows - cam_row) * res_m) ** 2 +
        ((visible_cols - cam_col) * res_m) ** 2
    )

    # Three zones: foreground (<1km), midground (1-5km), background (>5km)
    fg = np.sum(distances < 1000)
    mg = np.sum((distances >= 1000) & (distances < 5000))
    bg = np.sum(distances >= 5000)

    total = fg + mg + bg
    if total == 0:
        return 0.0

    # Evenness: 1 - coefficient of variation
    fractions = np.array([fg, mg, bg]) / total
    ideal = 1 / 3
    deviation = np.sqrt(np.mean((fractions - ideal) ** 2))

    return max(0.0, 1.0 - deviation * 3)


def _mystery_score(
    dem: np.ndarray,
    cam_row: int, cam_col: int, cam_z: float,
    res_m: float,
    viewshed: np.ndarray,
    interest_map: np.ndarray,
) -> float:
    """Mystery: ratio of interesting terrain just beyond visibility.

    From Kaplan & Kaplan: views where valleys curve out of sight
    or terrain promises "more beyond" score higher.
    """
    h, w = dem.shape

    # Find the visibility boundary (edge of viewshed)
    from scipy.ndimage import binary_dilation
    dilated = binary_dilation(viewshed, iterations=3)
    boundary = dilated & ~viewshed

    # Interesting terrain just beyond the boundary
    hidden_interest = interest_map[boundary].sum() if boundary.any() else 0
    visible_interest = interest_map[viewshed].sum()

    if visible_interest < 1e-10:
        return 0.0

    # Mystery = hidden interesting terrain / visible interesting terrain
    ratio = hidden_interest / visible_interest
    # Optimal around 0.3-0.5 (some hidden, but not everything)
    return min(1.0, ratio / 0.4) if ratio < 0.4 else max(0.0, 1.0 - (ratio - 0.4) / 0.6)


def _water_visibility(
    viewshed: np.ndarray, water_mask: np.ndarray
) -> float:
    """Fraction of water features that are visible."""
    total_water = water_mask.sum()
    if total_water == 0:
        return 0.0

    visible_water = (viewshed & water_mask).sum()
    return min(1.0, visible_water / max(total_water * 0.1, 1))
