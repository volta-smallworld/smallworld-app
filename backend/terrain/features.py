"""
Terrain feature extraction: peaks, ridgelines, cliffs, water, saddles.
All computed from DEM and its derivatives.
"""

import numpy as np
from scipy.ndimage import (
    label, maximum_filter, minimum_filter, uniform_filter, binary_dilation
)
from scipy.signal import argrelextrema
from dataclasses import dataclass, field
from typing import List, Tuple
from log import get_logger

log = get_logger("terrain.features")


@dataclass
class Feature:
    """A single terrain feature with position and properties."""
    type: str  # "peak", "ridge", "cliff", "stream", "lake", "saddle"
    row: int
    col: int
    elevation: float
    prominence: float = 0.0  # for peaks
    strength: float = 0.0  # feature intensity
    pixels: np.ndarray = field(default=None, repr=False)  # mask for extended features


@dataclass
class FeatureSet:
    """All extracted features from a DEM."""
    peaks: List[Feature]
    ridgelines: np.ndarray  # boolean mask
    cliffs: np.ndarray  # boolean mask
    streams: np.ndarray  # flow accumulation values
    lakes: np.ndarray  # boolean mask
    saddles: List[Feature]


def extract_features(
    dem: np.ndarray,
    derivatives: dict,
    res_m: float,
    min_prominence_m: float = 50.0,
) -> FeatureSet:
    """Extract all terrain features from DEM and derivatives."""
    log.info(f"Extracting features from DEM {dem.shape}, min_prominence={min_prominence_m}m")

    peaks = find_peaks(dem, res_m, min_prominence_m)
    log.info(f"Found {len(peaks)} peaks (top prominence: "
             f"{peaks[0].prominence:.0f}m)" if peaks else "Found 0 peaks")

    ridgelines = find_ridgelines(dem)
    log.info(f"Found {ridgelines.sum()} ridge cells")

    cliffs = find_cliffs(derivatives["profile_curvature"])
    log.info(f"Found {cliffs.sum()} cliff cells")

    streams, flow_acc = find_streams(dem)
    log.info(f"Found {streams.sum()} stream cells")

    lakes = find_lakes(dem)
    log.info(f"Found {lakes.sum()} lake cells")

    saddles = find_saddles(derivatives["gaussian_curvature"], dem)
    log.info(f"Found {len(saddles)} saddle points")

    return FeatureSet(
        peaks=peaks,
        ridgelines=ridgelines,
        cliffs=cliffs,
        streams=flow_acc,
        lakes=lakes,
        saddles=saddles,
    )


def find_peaks(
    dem: np.ndarray, res_m: float, min_prominence_m: float = 50.0
) -> List[Feature]:
    """Find peaks as local maxima filtered by topographic prominence.

    Prominence = minimum descent required to reach higher terrain.
    This separates real landmarks from noise bumps.
    """
    # Local maxima in a window proportional to resolution
    window = max(5, int(500 / res_m))  # ~500m neighborhood
    if window % 2 == 0:
        window += 1

    local_max = maximum_filter(dem, size=window)
    is_peak = (dem == local_max) & (dem > np.percentile(dem, 50))

    # Label connected components
    labeled, n_features = label(is_peak)

    peaks = []
    for i in range(1, n_features + 1):
        mask = labeled == i
        rows, cols = np.where(mask)
        # Take highest point in cluster
        idx = np.argmax(dem[rows, cols])
        r, c = rows[idx], cols[idx]
        elev = dem[r, c]

        # Compute prominence: find minimum drop needed to reach higher terrain
        prominence = compute_prominence(dem, r, c, elev)

        if prominence >= min_prominence_m:
            peaks.append(Feature(
                type="peak",
                row=r, col=c,
                elevation=elev,
                prominence=prominence,
                strength=prominence / 1000.0,  # normalize
            ))

    # Sort by prominence
    peaks.sort(key=lambda p: p.prominence, reverse=True)
    return peaks[:50]  # cap at 50 peaks


def compute_prominence(
    dem: np.ndarray, peak_row: int, peak_col: int, peak_elev: float,
    max_search_radius: int = 200
) -> float:
    """Approximate topographic prominence via expanding ring search.

    Find the minimum elevation on the path to any higher terrain.
    If no higher terrain exists in range, prominence = peak_elev - min(dem).
    """
    h, w = dem.shape

    # Search in expanding rings
    min_col_elev = peak_elev  # minimum elevation on col (saddle)

    for radius in range(5, max_search_radius, 5):
        r_min = max(0, peak_row - radius)
        r_max = min(h, peak_row + radius + 1)
        c_min = max(0, peak_col - radius)
        c_max = min(w, peak_col + radius + 1)

        ring = dem[r_min:r_max, c_min:c_max]

        if np.any(ring > peak_elev):
            # Higher terrain found — prominence is peak minus the
            # highest saddle point on the path (approximated by
            # the minimum value on the ring boundary)
            boundary = np.concatenate([
                ring[0, :], ring[-1, :], ring[:, 0], ring[:, -1]
            ])
            min_boundary = np.min(boundary)
            return peak_elev - min_boundary

    # No higher terrain found in search radius
    return peak_elev - np.min(dem)


def find_ridgelines(dem: np.ndarray) -> np.ndarray:
    """Find ridgelines using the inverted DEM hydrology trick.

    Invert DEM → run D8 flow accumulation → high-accumulation cells
    on inverted surface = ridgelines on real surface.
    """
    # Invert: valleys become peaks, ridges become valleys
    inverted = dem.max() - dem

    # D8 flow accumulation on inverted surface
    flow_acc = d8_flow_accumulation(inverted)

    # Threshold: cells with high flow accumulation = ridgelines
    threshold = np.percentile(flow_acc[flow_acc > 0], 95)
    ridgelines = flow_acc > threshold

    return ridgelines


def d8_flow_accumulation(dem: np.ndarray) -> np.ndarray:
    """D8 single-flow-direction flow accumulation.

    Each cell drains to its steepest downhill neighbor.
    Accumulation counts upstream contributing cells.
    """
    h, w = dem.shape
    flow_acc = np.ones((h, w), dtype=np.float64)

    # D8 directions: row_offset, col_offset
    dirs = [(-1, -1), (-1, 0), (-1, 1),
            (0, -1),           (0, 1),
            (1, -1),  (1, 0),  (1, 1)]
    diag_dist = np.sqrt(2)
    dists = [diag_dist, 1.0, diag_dist,
             1.0,             1.0,
             diag_dist, 1.0, diag_dist]

    # Compute flow direction for each cell
    flow_dir = np.full((h, w), -1, dtype=np.int8)

    for idx, (dr, dc) in enumerate(dirs):
        # Shifted elevation grid
        neighbor = np.full_like(dem, np.inf)
        r_src = slice(max(0, -dr), h + min(0, -dr))
        c_src = slice(max(0, -dc), w + min(0, -dc))
        r_dst = slice(max(0, dr), h + min(0, dr))
        c_dst = slice(max(0, dc), w + min(0, dc))
        neighbor[r_src, c_src] = dem[r_dst, c_dst]

        drop = (dem - neighbor) / dists[idx]

        # Update flow direction where this neighbor has steepest drop
        if idx == 0:
            best_drop = drop.copy()
            flow_dir[:] = idx
        else:
            better = drop > best_drop
            best_drop[better] = drop[better]
            flow_dir[better] = idx

    # Process cells from highest to lowest elevation
    sorted_indices = np.argsort(-dem.ravel())

    flat_acc = flow_acc.ravel()
    flat_dir = flow_dir.ravel()

    for flat_idx in sorted_indices:
        r = flat_idx // w
        c = flat_idx % w
        d = flat_dir[r * w + c]
        if d < 0:
            continue

        dr, dc = dirs[d]
        nr, nc = r + dr, c + dc
        if 0 <= nr < h and 0 <= nc < w:
            flat_acc[nr * w + nc] += flat_acc[r * w + c]

    return flat_acc.reshape(h, w)


def find_cliffs(profile_curvature: np.ndarray) -> np.ndarray:
    """Find cliffs where |profile curvature| exceeds 95th percentile."""
    abs_curv = np.abs(profile_curvature)
    threshold = np.percentile(abs_curv, 95)
    return abs_curv > threshold


def find_streams(dem: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Find streams via D8 flow accumulation on normal DEM.
    Returns (stream_mask, flow_accumulation).
    """
    flow_acc = d8_flow_accumulation(dem)
    threshold = np.percentile(flow_acc[flow_acc > 1], 90)
    streams = flow_acc > threshold
    return streams, flow_acc


def find_lakes(dem: np.ndarray) -> np.ndarray:
    """Find lakes by filling depressions and checking where fill > original.

    Cells where filled DEM exceeds original by threshold = lake bed.
    Uses iterative depression filling (simplified Priority-Flood).
    """
    filled = fill_depressions(dem)
    diff = filled - dem
    # Lake where fill depth > 1 meter
    return diff > 1.0


def fill_depressions(dem: np.ndarray) -> np.ndarray:
    """Simplified depression filling using iterative approach.
    Fills all closed depressions so water can drain to edges.
    """
    h, w = dem.shape
    filled = np.full_like(dem, np.inf)

    # Set boundary cells to their actual elevation
    filled[0, :] = dem[0, :]
    filled[-1, :] = dem[-1, :]
    filled[:, 0] = dem[:, 0]
    filled[:, -1] = dem[:, -1]

    # Iteratively lower interior cells
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1)]

    changed = True
    iterations = 0
    while changed and iterations < 100:
        changed = False
        iterations += 1
        for dr, dc in dirs:
            # Shift the filled array
            shifted = np.roll(np.roll(filled, -dr, axis=0), -dc, axis=1)
            # New value = max(dem, min(current filled, shifted neighbor))
            new_val = np.maximum(dem, np.minimum(filled, shifted))

            # Only update interior
            mask = (new_val < filled)
            mask[0, :] = mask[-1, :] = mask[:, 0] = mask[:, -1] = False

            if np.any(mask):
                filled[mask] = new_val[mask]
                changed = True

    return filled


def find_saddles(
    gaussian_curvature: np.ndarray, dem: np.ndarray
) -> List[Feature]:
    """Find saddle points where Gaussian curvature is strongly negative.
    Mountain passes: terrain curves up in one direction, down in another.
    """
    threshold = np.percentile(gaussian_curvature, 2)  # bottom 2%
    saddle_mask = gaussian_curvature < threshold

    # Cluster and take representative points
    labeled, n_features = label(saddle_mask)
    saddles = []

    for i in range(1, min(n_features + 1, 30)):  # cap at 30
        mask = labeled == i
        rows, cols = np.where(mask)
        if len(rows) < 3:
            continue

        # Representative point: centroid
        r = int(np.mean(rows))
        c = int(np.mean(cols))

        saddles.append(Feature(
            type="saddle",
            row=r, col=c,
            elevation=dem[r, c],
            strength=abs(gaussian_curvature[r, c]),
        ))

    saddles.sort(key=lambda s: s.strength, reverse=True)
    return saddles[:20]
