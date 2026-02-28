"""
Interest map computation: weighted combination of all terrain features.
Produces a heatmap showing where the "interesting" terrain is.
"""

import numpy as np
from scipy.ndimage import gaussian_filter
from .features import FeatureSet
from config import DEFAULT_FEATURE_WEIGHTS
from log import get_logger

log = get_logger("terrain.interest")


def compute_interest_map(
    dem: np.ndarray,
    features: FeatureSet,
    derivatives: dict,
    weights: dict = None,
) -> np.ndarray:
    """Compute interest map from terrain features.

    Args:
        dem: elevation grid
        features: extracted FeatureSet
        derivatives: terrain derivatives dict
        weights: feature weight overrides (keys: peaks, ridges, cliffs, water, relief)

    Returns:
        (H, W) float64 interest map, 0-1 normalized
    """
    w = {**DEFAULT_FEATURE_WEIGHTS, **(weights or {})}
    h, width = dem.shape

    log.info(f"Computing interest map {h}x{width}, weights: {w}")

    interest = np.zeros_like(dem, dtype=np.float64)

    # Peaks: distance-decayed influence
    if features.peaks and w["peaks"] > 0:
        peak_map = np.zeros_like(dem)
        for peak in features.peaks:
            peak_map[peak.row, peak.col] = peak.prominence
        # Gaussian decay — sigma proportional to peak importance
        peak_influence = gaussian_filter(peak_map, sigma=30)
        interest += w["peaks"] * normalize(peak_influence)

    # Ridgelines: binary mask, slight blur for smooth gradient
    if w["ridges"] > 0:
        ridge_float = features.ridgelines.astype(np.float64)
        ridge_influence = gaussian_filter(ridge_float, sigma=5)
        interest += w["ridges"] * normalize(ridge_influence)

    # Cliffs: curvature magnitude
    if w["cliffs"] > 0:
        cliff_float = features.cliffs.astype(np.float64)
        cliff_influence = gaussian_filter(cliff_float, sigma=8)
        interest += w["cliffs"] * normalize(cliff_influence)

    # Water: streams + lakes
    if w["water"] > 0:
        water_map = np.zeros_like(dem)
        # Streams from flow accumulation
        stream_mask = features.streams > np.percentile(features.streams, 90)
        water_map[stream_mask] = 1.0
        # Lakes
        water_map[features.lakes] = 1.5  # lakes are extra interesting
        water_influence = gaussian_filter(water_map, sigma=15)
        interest += w["water"] * normalize(water_influence)

    # Relief: local elevation range
    if w["relief"] > 0:
        from .analysis import local_elevation_range
        relief = local_elevation_range(dem, window=21)
        interest += w["relief"] * normalize(relief)

    # Normalize final interest map to 0-1
    result = normalize(interest)
    log.info(f"Interest map computed, hot-spot coverage: "
             f"{(result > 0.5).sum() / result.size * 100:.1f}%")
    return result


def normalize(arr: np.ndarray) -> np.ndarray:
    """Normalize array to 0-1 range."""
    vmin, vmax = arr.min(), arr.max()
    if vmax - vmin < 1e-10:
        return np.zeros_like(arr)
    return (arr - vmin) / (vmax - vmin)


def distance_decay(
    feature_mask: np.ndarray, sigma_pixels: float = 30
) -> np.ndarray:
    """Create distance-decayed influence from a binary feature mask."""
    return gaussian_filter(feature_mask.astype(np.float64), sigma=sigma_pixels)
