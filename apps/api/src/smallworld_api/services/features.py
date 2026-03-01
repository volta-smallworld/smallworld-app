"""Lightweight terrain feature extraction on a 128x128 DEM grid."""

from __future__ import annotations

from heapq import heappop, heappush
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
MIN_PATH_SMOOTH_VERTICES = 10
PATH_SMOOTH_SIGMA_CELLS = 1.0
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


def _build_component_adjacency(coords: np.ndarray) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Build 8-neighbor adjacency for a connected component."""
    component = {(int(r), int(c)) for r, c in coords}
    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for r, c in component:
        neighbors: list[tuple[int, int]] = []
        for dr, dc in _D8_OFFSETS:
            candidate = (r + dr, c + dc)
            if candidate in component:
                neighbors.append(candidate)
        adjacency[(r, c)] = neighbors
    return adjacency


def _farthest_cell(origin: tuple[int, int], cells: np.ndarray) -> tuple[int, int]:
    """Return the cell farthest (Euclidean) from origin."""
    dr = cells[:, 0] - origin[0]
    dc = cells[:, 1] - origin[1]
    idx = int(np.argmax(dr * dr + dc * dc))
    return (int(cells[idx, 0]), int(cells[idx, 1]))


def _pick_component_endpoints(
    adjacency: dict[tuple[int, int], list[tuple[int, int]]]
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Pick stable endpoints for tracing the principal path through a component."""
    all_cells = np.array(list(adjacency.keys()), dtype=np.int32)
    endpoint_cells = np.array(
        [cell for cell, neighbors in adjacency.items() if len(neighbors) <= 1], dtype=np.int32
    )
    candidates = endpoint_cells if len(endpoint_cells) >= 2 else all_cells

    seed_idx = int(np.lexsort((candidates[:, 1], candidates[:, 0]))[0])
    seed = (int(candidates[seed_idx, 0]), int(candidates[seed_idx, 1]))
    start = _farthest_cell(seed, candidates)
    end = _farthest_cell(start, candidates)

    if start == end and len(candidates) > 1:
        dr = candidates[:, 0] - start[0]
        dc = candidates[:, 1] - start[1]
        order = np.argsort(dr * dr + dc * dc)
        second = candidates[int(order[-2])]
        end = (int(second[0]), int(second[1]))

    return start, end


def _trace_component_path(coords: np.ndarray) -> np.ndarray:
    """Trace a connected path across a component from one endpoint to the other."""
    if len(coords) == 0:
        return np.zeros((0, 2), dtype=np.float64)
    if len(coords) == 1:
        return np.array([[float(coords[0, 0]), float(coords[0, 1])]], dtype=np.float64)

    adjacency = _build_component_adjacency(coords)
    start, end = _pick_component_endpoints(adjacency)

    if start == end:
        return np.array([[float(start[0]), float(start[1])]], dtype=np.float64)

    dist: dict[tuple[int, int], float] = {start: 0.0}
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    heap: list[tuple[float, tuple[int, int]]] = [(0.0, start)]

    while heap:
        cur_dist, node = heappop(heap)
        if cur_dist > dist.get(node, float("inf")):
            continue
        if node == end:
            break
        for nbr in adjacency[node]:
            diagonal = nbr[0] != node[0] and nbr[1] != node[1]
            step_cost = math.sqrt(2.0) if diagonal else 1.0
            new_dist = cur_dist + step_cost
            if new_dist < dist.get(nbr, float("inf")):
                dist[nbr] = new_dist
                prev[nbr] = node
                heappush(heap, (new_dist, nbr))

    if end not in dist:
        # Fallback should be rare; component labeling implies connectivity.
        return np.array([[float(start[0]), float(start[1])], [float(end[0]), float(end[1])]])

    path: list[tuple[int, int]] = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()

    return np.array([(float(r), float(c)) for r, c in path], dtype=np.float64)


def _resample_path(path_rc: np.ndarray, max_vertices: int) -> np.ndarray:
    """Resample polyline to a fixed vertex budget with arc-length interpolation."""
    if len(path_rc) <= max_vertices:
        return path_rc

    seg_lengths = np.linalg.norm(np.diff(path_rc, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(seg_lengths)))
    total_length = float(cumulative[-1])

    if total_length <= 1e-9:
        idx = np.linspace(0, len(path_rc) - 1, max_vertices, dtype=int)
        return path_rc[idx]

    targets = np.linspace(0.0, total_length, max_vertices)
    rows = np.interp(targets, cumulative, path_rc[:, 0])
    cols = np.interp(targets, cumulative, path_rc[:, 1])
    resampled = np.column_stack((rows, cols))
    resampled[0] = path_rc[0]
    resampled[-1] = path_rc[-1]
    return resampled


def _smooth_path(path_rc: np.ndarray) -> np.ndarray:
    """Lightly smooth a traced path to reduce DEM cell stair-stepping artifacts."""
    if len(path_rc) < MIN_PATH_SMOOTH_VERTICES:
        return path_rc

    smoothed = np.column_stack(
        (
            ndimage.gaussian_filter1d(path_rc[:, 0], sigma=PATH_SMOOTH_SIGMA_CELLS, mode="nearest"),
            ndimage.gaussian_filter1d(path_rc[:, 1], sigma=PATH_SMOOTH_SIGMA_CELLS, mode="nearest"),
        )
    )
    smoothed[0] = path_rc[0]
    smoothed[-1] = path_rc[-1]
    return smoothed


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
        traced = _trace_component_path(coords)
        traced = _smooth_path(traced)
        traced = _resample_path(traced, max_vertices)
        path = [_grid_to_latlng(r, c, bounds, grid_h, grid_w) for r, c in traced]
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
