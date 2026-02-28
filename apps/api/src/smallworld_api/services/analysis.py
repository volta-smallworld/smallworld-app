"""Build a weighted interest surface and extract hotspots from terrain features."""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from smallworld_api.services.tiles import GeoBounds

MAX_HOTSPOTS_RETURNED = 10

DEFAULT_ANALYSIS_WEIGHTS = {
    "peaks": 1.0,
    "ridges": 0.9,
    "cliffs": 0.8,
    "water": 0.7,
    "relief": 1.0,
}
EIGHT_CONNECTED = ndimage.generate_binary_structure(2, 2)


def _normalize(arr: np.ndarray) -> np.ndarray:
    """Min-max normalize to [0, 1]."""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-12:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


def _point_distance_field(
    grid_h: int, grid_w: int, points: list[dict], bounds: GeoBounds, sigma_cells: float = 5.0
) -> np.ndarray:
    """Gaussian distance-decay surface for a list of point features with center/score."""
    surface = np.zeros((grid_h, grid_w), dtype=np.float64)
    if not points:
        return surface
    for pt in points:
        # Map lat/lng back to grid coords
        r = (bounds.north - pt["center"]["lat"]) / (bounds.north - bounds.south) * (grid_h - 1)
        c = (pt["center"]["lng"] - bounds.west) / (bounds.east - bounds.west) * (grid_w - 1)
        r = max(0.0, min(float(grid_h - 1), r))
        c = max(0.0, min(float(grid_w - 1), c))
        score = pt.get("score", 1.0)
        rr, cc = np.ogrid[:grid_h, :grid_w]
        dist_sq = (rr - r) ** 2 + (cc - c) ** 2
        surface += score * np.exp(-dist_sq / (2 * sigma_cells**2))
    return _normalize(surface) if surface.max() > 0 else surface


def _line_mask(
    grid_h: int, grid_w: int, features: list[dict], bounds: GeoBounds, width_cells: int = 2
) -> np.ndarray:
    """Rasterize line features (with path field) into a binary mask then dilate."""
    mask = np.zeros((grid_h, grid_w), dtype=bool)
    for feat in features:
        path = feat.get("path", [])
        for pt in path:
            r = int(
                round(
                    (bounds.north - pt["lat"])
                    / (bounds.north - bounds.south)
                    * (grid_h - 1)
                )
            )
            c = int(
                round(
                    (pt["lng"] - bounds.west) / (bounds.east - bounds.west) * (grid_w - 1)
                )
            )
            r = max(0, min(grid_h - 1, r))
            c = max(0, min(grid_w - 1, c))
            mask[r, c] = True
    if width_cells > 1:
        struct = ndimage.generate_binary_structure(2, 1)
        mask = ndimage.binary_dilation(mask, structure=struct, iterations=width_cells // 2)
    return mask


def build_interest_raster(
    dem: np.ndarray,
    local_relief: np.ndarray,
    curvature: np.ndarray,
    peaks: list[dict],
    ridges: list[dict],
    cliffs: list[dict],
    water_channels: list[dict],
    bounds: GeoBounds,
    weights: dict[str, float],
) -> np.ndarray:
    """Combine feature layers into a single [0,1] interest raster."""
    h, w = dem.shape
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return np.zeros((h, w), dtype=np.float64)

    layers: list[tuple[str, np.ndarray]] = []

    # Peaks: Gaussian decay from peak locations
    if weights.get("peaks", 0) > 0:
        layers.append(("peaks", _point_distance_field(h, w, peaks, bounds)))

    # Ridges: rasterized mask, normalized
    if weights.get("ridges", 0) > 0:
        ridge_mask = _line_mask(h, w, ridges, bounds).astype(np.float64)
        layers.append(("ridges", _normalize(ndimage.gaussian_filter(ridge_mask, sigma=2.0))))

    # Cliffs: distance-decay from cliff centroids
    if weights.get("cliffs", 0) > 0:
        layers.append(("cliffs", _point_distance_field(h, w, cliffs, bounds)))

    # Water: distance-decay from channel paths (use path points as pseudo-points)
    if weights.get("water", 0) > 0:
        water_pts = []
        for ch in water_channels:
            for pt in ch.get("path", []):
                water_pts.append({"center": pt, "score": ch.get("score", 1.0)})
        layers.append(("water", _point_distance_field(h, w, water_pts, bounds, sigma_cells=3.0)))

    # Relief: normalized local relief
    if weights.get("relief", 0) > 0:
        layers.append(("relief", _normalize(local_relief)))

    interest = np.zeros((h, w), dtype=np.float64)
    for name, layer in layers:
        interest += weights.get(name, 0) * layer
    interest /= total_weight
    return np.clip(interest, 0, 1)


def extract_hotspots(
    interest: np.ndarray,
    bounds: GeoBounds,
    weights: dict[str, float],
    layer_contributions: dict[str, np.ndarray],
    max_count: int = MAX_HOTSPOTS_RETURNED,
) -> list[dict]:
    """Find top local maxima in the interest raster as hotspots with reason tags."""
    h, w = interest.shape
    local_max = ndimage.maximum_filter(interest, size=7)
    hotspot_mask = (interest == local_max) & (interest > 0.1)
    labeled, n_labels = ndimage.label(hotspot_mask, structure=EIGHT_CONNECTED)
    if n_labels == 0:
        return []

    layer_names = [name for name in layer_contributions if weights.get(name, 0) > 0]
    candidates: list[tuple[float, int, int]] = []
    for label_id in range(1, n_labels + 1):
        coords = np.argwhere(labeled == label_id)
        if len(coords) == 0:
            continue

        component_scores = np.array([interest[r, c] for r, c in coords])
        best_score = float(component_scores.max())
        top_coords = coords[np.isclose(component_scores, best_score)]
        centroid = coords.mean(axis=0)
        distances = np.sum((top_coords - centroid) ** 2, axis=1)
        best_r, best_c = top_coords[int(np.argmin(distances))]
        candidates.append((best_score, int(best_r), int(best_c)))

    candidates.sort(key=lambda item: -item[0])
    candidates = candidates[:max_count]

    hotspots = []
    for idx, (score, r, c) in enumerate(candidates):
        contribs = {
            name: float(layer_contributions[name][r, c]) * weights.get(name, 0)
            for name in layer_names
        }
        reasons = sorted(contribs, key=lambda k: -contribs[k])[:3]
        reasons = [reason for reason in reasons if contribs[reason] > 0.05]

        hotspots.append(
            {
                "id": f"hotspot-{idx + 1}",
                "center": {
                    "lat": round(
                        bounds.north - (r / (h - 1)) * (bounds.north - bounds.south), 6
                    ),
                    "lng": round(
                        bounds.west + (c / (w - 1)) * (bounds.east - bounds.west), 6
                    ),
                },
                "score": round(score, 2),
                "reasons": reasons,
            }
        )
    return hotspots


def build_layer_contributions(
    dem: np.ndarray,
    local_relief: np.ndarray,
    curvature: np.ndarray,
    peaks: list[dict],
    ridges: list[dict],
    cliffs: list[dict],
    water_channels: list[dict],
    bounds: GeoBounds,
) -> dict[str, np.ndarray]:
    """Build individual normalized layers for reason attribution."""
    h, w = dem.shape
    layers: dict[str, np.ndarray] = {}
    layers["peaks"] = _point_distance_field(h, w, peaks, bounds)
    ridge_mask = _line_mask(h, w, ridges, bounds).astype(np.float64)
    layers["ridges"] = _normalize(ndimage.gaussian_filter(ridge_mask, sigma=2.0))
    layers["cliffs"] = _point_distance_field(h, w, cliffs, bounds)
    water_pts = []
    for ch in water_channels:
        for pt in ch.get("path", []):
            water_pts.append({"center": pt, "score": ch.get("score", 1.0)})
    layers["water"] = _point_distance_field(h, w, water_pts, bounds, sigma_cells=3.0)
    layers["relief"] = _normalize(local_relief)
    return layers
