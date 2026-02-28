"""Lightweight terrain feature extraction on a 128x128 DEM grid."""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from smallworld_api.services.tiles import GeoBounds

# ── Defaults ─────────────────────────────────────────────────────────────────

PEAK_MIN_PROMINENCE_METERS_APPROX = 120
CLIFF_MIN_SLOPE_DEGREES = 30
FLOW_MIN_ACCUMULATION_CELLS = 24
MAX_FEATURES_PER_KIND = 25
MAX_PATH_VERTICES = 24
MIN_PATH_CELLS = 5
EIGHT_CONNECTED = ndimage.generate_binary_structure(2, 2)

# ── Coordinate helpers ───────────────────────────────────────────────────────


def _grid_to_latlng(
    row: int | float, col: int | float, bounds: GeoBounds, grid_h: int, grid_w: int
) -> dict:
    lat = bounds.north - (row / (grid_h - 1)) * (bounds.north - bounds.south)
    lng = bounds.west + (col / (grid_w - 1)) * (bounds.east - bounds.west)
    return {"lat": round(lat, 6), "lng": round(lng, 6)}


def _path_length_meters(path: list[dict], cell_size: float, grid_h: int, grid_w: int) -> float:
    """Approximate path length from lat/lng points using equirectangular distance."""
    if len(path) < 2:
        return 0.0
    total = 0.0
    R = 6378137.0
    for a, b in zip(path, path[1:]):
        dlat = math.radians(b["lat"] - a["lat"])
        dlng = math.radians(b["lng"] - a["lng"])
        mid_lat = math.radians((a["lat"] + b["lat"]) / 2)
        dx = dlng * math.cos(mid_lat) * R
        dy = dlat * R
        total += math.sqrt(dx**2 + dy**2)
    return total


# ── D8 flow accumulation ────────────────────────────────────────────────────

# 8-connected neighbor offsets: (drow, dcol)
_D8_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_D8_DISTANCES = [math.sqrt(2), 1.0, math.sqrt(2), 1.0, 1.0, math.sqrt(2), 1.0, math.sqrt(2)]


def _d8_flow_direction(dem: np.ndarray) -> np.ndarray:
    """Return D8 flow direction grid. Each cell contains the index (0-7) of the
    steepest downhill neighbor, or -1 for flat/pit cells."""
    h, w = dem.shape
    flow_dir = np.full((h, w), -1, dtype=np.int8)
    for r in range(h):
        for c in range(w):
            max_drop = 0.0
            best = -1
            for i, (dr, dc) in enumerate(_D8_OFFSETS):
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w:
                    drop = (dem[r, c] - dem[nr, nc]) / _D8_DISTANCES[i]
                    if drop > max_drop:
                        max_drop = drop
                        best = i
            flow_dir[r, c] = best
    return flow_dir


def _d8_accumulation(flow_dir: np.ndarray) -> np.ndarray:
    """Count upstream cells for each cell following the flow direction grid."""
    h, w = flow_dir.shape
    acc = np.ones((h, w), dtype=np.int32)
    # Build reverse adjacency: which cells flow into each cell
    inflow_count = np.zeros((h, w), dtype=np.int32)
    for r in range(h):
        for c in range(w):
            d = flow_dir[r, c]
            if d >= 0:
                dr, dc = _D8_OFFSETS[d]
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w:
                    inflow_count[nr, nc] += 1

    # Topological sort — start from headwater cells (no inflow)
    stack = []
    for r in range(h):
        for c in range(w):
            if inflow_count[r, c] == 0:
                stack.append((r, c))

    while stack:
        r, c = stack.pop()
        d = flow_dir[r, c]
        if d >= 0:
            dr, dc = _D8_OFFSETS[d]
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                acc[nr, nc] += acc[r, c]
                inflow_count[nr, nc] -= 1
                if inflow_count[nr, nc] == 0:
                    stack.append((nr, nc))
    return acc


# ── Connected-component path tracing ────────────────────────────────────────


def _mask_to_paths(
    mask: np.ndarray,
    bounds: GeoBounds,
    dem: np.ndarray,
    cell_size: float,
    min_cells: int = MIN_PATH_CELLS,
    max_vertices: int = MAX_PATH_VERTICES,
) -> list[dict]:
    """Convert a boolean mask into a list of path features (one per component)."""
    labeled, n_labels = ndimage.label(mask, structure=EIGHT_CONNECTED)
    grid_h, grid_w = mask.shape
    paths = []
    for label_id in range(1, n_labels + 1):
        coords = np.argwhere(labeled == label_id)
        if len(coords) < min_cells:
            continue
        # Sort by row to get a rough top-to-bottom path
        coords = coords[coords[:, 0].argsort()]
        # Subsample
        if len(coords) > max_vertices:
            indices = np.linspace(0, len(coords) - 1, max_vertices, dtype=int)
            coords = coords[indices]
        path = [_grid_to_latlng(r, c, bounds, grid_h, grid_w) for r, c in coords]
        length_m = _path_length_meters(path, cell_size, grid_h, grid_w)
        paths.append({"path": path, "lengthMetersApprox": round(length_m)})
    return paths


# ── Public extraction functions ──────────────────────────────────────────────


def extract_peaks(
    dem: np.ndarray,
    bounds: GeoBounds,
    min_prominence: float = PEAK_MIN_PROMINENCE_METERS_APPROX,
    max_count: int = MAX_FEATURES_PER_KIND,
) -> list[dict]:
    """Detect peaks as 3x3 local maxima with approximate prominence filter."""
    h, w = dem.shape
    # 3x3 local max
    local_max = ndimage.maximum_filter(dem, size=3)
    is_peak = (dem == local_max) & (dem > np.min(dem))

    # Prominence: diff from min in 11x11 neighborhood
    local_min_11 = ndimage.minimum_filter(dem, size=11)
    prominence = dem - local_min_11

    peak_mask = is_peak & (prominence >= min_prominence)
    labeled, n_labels = ndimage.label(peak_mask, structure=EIGHT_CONNECTED)
    if n_labels == 0:
        return []

    candidates: list[tuple[float, float, int, int]] = []
    for label_id in range(1, n_labels + 1):
        coords = np.argwhere(labeled == label_id)
        if len(coords) == 0:
            continue

        component_proms = np.array([prominence[r, c] for r, c in coords])
        component_elevs = np.array([dem[r, c] for r, c in coords])
        best_prom = float(component_proms.max())
        best_elev = float(component_elevs.max())

        top_coords = coords[
            np.isclose(component_proms, best_prom) & np.isclose(component_elevs, best_elev)
        ]
        centroid = coords.mean(axis=0)
        distances = np.sum((top_coords - centroid) ** 2, axis=1)
        best_r, best_c = top_coords[int(np.argmin(distances))]
        candidates.append((best_prom, best_elev, int(best_r), int(best_c)))

    candidates.sort(key=lambda item: (-item[0], -item[1]))
    candidates = candidates[:max_count]
    max_prom = max((candidate[0] for candidate in candidates), default=1.0) or 1.0

    peaks = []
    for idx, (prom, elev, r, c) in enumerate(candidates):
        peaks.append(
            {
                "id": f"peak-{idx + 1}",
                "center": _grid_to_latlng(r, c, bounds, h, w),
                "elevationMeters": round(elev, 1),
                "prominenceMetersApprox": round(prom, 1),
                "score": round(prom / max_prom, 2),
            }
        )
    return peaks


def extract_water_channels(
    dem: np.ndarray,
    bounds: GeoBounds,
    cell_size: float,
    threshold: int = FLOW_MIN_ACCUMULATION_CELLS,
    max_count: int = MAX_FEATURES_PER_KIND,
) -> list[dict]:
    """Extract water channels via D8 flow accumulation on the DEM."""
    flow_dir = _d8_flow_direction(dem)
    acc = _d8_accumulation(flow_dir)
    channel_mask = acc >= threshold
    paths = _mask_to_paths(channel_mask, bounds, dem, cell_size)

    # Score by length
    if not paths:
        return []
    max_len = max(p["lengthMetersApprox"] for p in paths) or 1
    for i, p in enumerate(sorted(paths, key=lambda x: -x["lengthMetersApprox"])[:max_count]):
        p["id"] = f"water-{i + 1}"
        p["score"] = round(p["lengthMetersApprox"] / max_len, 2)

    paths.sort(key=lambda x: -x.get("score", 0))
    return paths[:max_count]


def extract_ridges(
    dem: np.ndarray,
    bounds: GeoBounds,
    cell_size: float,
    threshold: int = FLOW_MIN_ACCUMULATION_CELLS,
    max_count: int = MAX_FEATURES_PER_KIND,
) -> list[dict]:
    """Extract ridges via D8 flow accumulation on the inverted DEM."""
    inverted = dem.max() - dem
    flow_dir = _d8_flow_direction(inverted)
    acc = _d8_accumulation(flow_dir)
    ridge_mask = acc >= threshold
    paths = _mask_to_paths(ridge_mask, bounds, dem, cell_size)

    if not paths:
        return []
    max_len = max(p["lengthMetersApprox"] for p in paths) or 1
    for i, p in enumerate(sorted(paths, key=lambda x: -x["lengthMetersApprox"])[:max_count]):
        p["id"] = f"ridge-{i + 1}"
        p["score"] = round(p["lengthMetersApprox"] / max_len, 2)

    paths.sort(key=lambda x: -x.get("score", 0))
    return paths[:max_count]


def extract_cliffs(
    slope: np.ndarray,
    curvature: np.ndarray,
    bounds: GeoBounds,
    dem: np.ndarray,
    min_slope: float = CLIFF_MIN_SLOPE_DEGREES,
    max_count: int = MAX_FEATURES_PER_KIND,
) -> list[dict]:
    """Detect cliffs as clusters of steep slope + high curvature magnitude."""
    h, w = slope.shape
    abs_curv = np.abs(curvature)
    curv_p95 = np.percentile(abs_curv, 95) if abs_curv.size > 0 else 0.0

    cliff_mask = (slope >= min_slope) & (abs_curv >= curv_p95)
    labeled, n_labels = ndimage.label(cliff_mask)
    if n_labels == 0:
        return []

    cliffs = []
    for label_id in range(1, n_labels + 1):
        coords = np.argwhere(labeled == label_id)
        if len(coords) < 2:
            continue
        centroid_r = coords[:, 0].mean()
        centroid_c = coords[:, 1].mean()
        # Drop estimate: max - min elevation in cluster
        elevs = np.array([dem[r, c] for r, c in coords])
        drop = float(elevs.max() - elevs.min())
        mean_slope = float(np.mean([slope[r, c] for r, c in coords]))
        cliffs.append(
            {
                "centroid": (centroid_r, centroid_c),
                "dropMetersApprox": round(drop, 1),
                "meanSlope": mean_slope,
                "size": len(coords),
            }
        )

    # Score by drop, sort descending
    if not cliffs:
        return []
    max_drop = max(c["dropMetersApprox"] for c in cliffs) or 1.0
    cliffs.sort(key=lambda x: -x["dropMetersApprox"])
    cliffs = cliffs[:max_count]

    result = []
    for i, c in enumerate(cliffs):
        r, col = c["centroid"]
        result.append(
            {
                "id": f"cliff-{i + 1}",
                "center": _grid_to_latlng(r, col, bounds, h, w),
                "dropMetersApprox": c["dropMetersApprox"],
                "score": round(c["dropMetersApprox"] / max_drop, 2),
            }
        )
    return result
