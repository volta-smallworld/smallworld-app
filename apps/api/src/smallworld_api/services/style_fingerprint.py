"""Structural fingerprint extraction for style references.

Normalises uploaded images, runs HED edge detection, skeletonises the
edge map, and builds a 100-dimensional fingerprint vector used for
DEM-patch matching and render verification.
"""

from __future__ import annotations

import logging
import math
from io import BytesIO

import cv2
import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
from PIL import Image
from skimage.morphology import skeletonize

from smallworld_api.config import settings

logger = logging.getLogger(__name__)

_MAX_SIDE = 512
_FINGERPRINT_DIM = 100

# Lazy-loaded HED network
_hed_net: cv2.dnn.Net | None = None
_hed_loaded: bool | None = None


def _load_hed() -> bool:
    """Attempt to load the HED network. Returns True on success."""
    global _hed_net, _hed_loaded
    if _hed_loaded is not None:
        return _hed_loaded
    proto = settings.style_hed_prototxt_path
    weights = settings.style_hed_weights_path
    if not proto or not weights:
        logger.warning("HED model paths not configured")
        _hed_loaded = False
        return False
    try:
        _hed_net = cv2.dnn.readNetFromCaffe(proto, weights)
        _hed_loaded = True
        logger.info("HED network loaded successfully")
    except Exception:
        logger.exception("Failed to load HED network")
        _hed_loaded = False
    return _hed_loaded


def is_hed_available() -> bool:
    """Check whether the HED network can be loaded."""
    return _load_hed()


# ── Image normalisation ──────────────────────────────────────────────────────


def normalize_image(raw_bytes: bytes) -> tuple[np.ndarray, int, int]:
    """Decode and resize an image to RGB with max side ``_MAX_SIDE``.

    Returns ``(rgb_array, original_width, original_height)``.
    """
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    orig_w, orig_h = img.size

    # Resize so max side is _MAX_SIDE
    scale = min(_MAX_SIDE / max(orig_w, orig_h), 1.0)
    if scale < 1.0:
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return np.array(img), orig_w, orig_h


# ── HED edge detection ──────────────────────────────────────────────────────


def _run_hed(rgb: np.ndarray) -> np.ndarray:
    """Run HED edge detection and return a float32 edge map in [0, 1]."""
    if not _load_hed() or _hed_net is None:
        # Fallback: Canny edges
        return _canny_fallback(rgb)

    h, w = rgb.shape[:2]
    blob = cv2.dnn.blobFromImage(
        rgb,
        scalefactor=1.0,
        size=(w, h),
        mean=(104.00698793, 116.66876762, 122.67891434),
        swapRB=False,
        crop=False,
    )
    _hed_net.setInput(blob)
    out = _hed_net.forward()
    edge_map = out[0, 0]
    edge_map = np.clip(edge_map, 0, 1).astype(np.float32)
    return edge_map


def _canny_fallback(rgb: np.ndarray) -> np.ndarray:
    """Canny-based fallback when HED is unavailable."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    return (edges / 255.0).astype(np.float32)


# ── Skeleton and descriptors ────────────────────────────────────────────────


def _skeletonize_edges(edge_map: np.ndarray, threshold: float = 0.3) -> np.ndarray:
    """Binarise and skeletonise the edge map."""
    binary = (edge_map > threshold).astype(np.uint8)
    skeleton = skeletonize(binary).astype(np.float32)
    return skeleton


def _compute_curvature_at_points(
    skeleton: np.ndarray,
) -> np.ndarray:
    """Estimate curvature at each skeleton pixel using Sobel derivatives."""
    # Compute gradients on the skeleton
    dx = cv2.Sobel(skeleton, cv2.CV_32F, 1, 0, ksize=3)
    dy = cv2.Sobel(skeleton, cv2.CV_32F, 0, 1, ksize=3)
    dxx = cv2.Sobel(dx, cv2.CV_32F, 1, 0, ksize=3)
    dyy = cv2.Sobel(dy, cv2.CV_32F, 0, 1, ksize=3)
    dxy = cv2.Sobel(dx, cv2.CV_32F, 0, 1, ksize=3)

    # Curvature = |dxx*dyy - dxy^2| / (dx^2 + dy^2 + eps)^1.5
    denom = (dx**2 + dy**2 + 1e-8) ** 1.5
    curvature = np.abs(dxx * dyy - dxy**2) / denom
    # Only at skeleton points
    curvature = curvature * (skeleton > 0).astype(np.float32)
    return curvature


def _compute_orientation_at_points(skeleton: np.ndarray) -> np.ndarray:
    """Estimate orientation (in radians) at each skeleton pixel."""
    dx = cv2.Sobel(skeleton, cv2.CV_32F, 1, 0, ksize=3)
    dy = cv2.Sobel(skeleton, cv2.CV_32F, 0, 1, ksize=3)
    orientation = np.arctan2(dy, dx)
    # Only at skeleton points
    mask = skeleton > 0
    orientation = orientation * mask.astype(np.float32)
    return orientation


# ── Fingerprint vector construction ─────────────────────────────────────────


def _build_fingerprint_vector(
    skeleton: np.ndarray,
    curvature: np.ndarray,
    orientation: np.ndarray,
    edge_map: np.ndarray,
) -> tuple[np.ndarray, dict]:
    """Build the 100-dim fingerprint vector.

    Layout:
      12-bin curvature histogram × 4 quadrants = 48
      8-bin orientation histogram × 4 quadrants = 32
      4×4 spatial density grid = 16
      parallelism score = 1
      dominant orientation = 1
      vertical centroid = 1
      feature scale estimate = 1
      total = 100
    """
    h, w = skeleton.shape
    mid_y, mid_x = h // 2, w // 2
    mask = skeleton > 0

    # Define quadrants: TL, TR, BL, BR
    quadrant_slices = [
        (slice(0, mid_y), slice(0, mid_x)),      # TL
        (slice(0, mid_y), slice(mid_x, w)),       # TR
        (slice(mid_y, h), slice(0, mid_x)),       # BL
        (slice(mid_y, h), slice(mid_x, w)),       # BR
    ]

    vector_parts: list[np.ndarray] = []

    # Curvature histograms per quadrant (12 bins × 4 = 48)
    curv_max = float(np.max(curvature)) if np.max(curvature) > 0 else 1.0
    for ys, xs in quadrant_slices:
        q_mask = mask[ys, xs]
        q_curv = curvature[ys, xs]
        vals = q_curv[q_mask]
        if len(vals) == 0:
            hist = np.zeros(12, dtype=np.float32)
        else:
            hist, _ = np.histogram(vals, bins=12, range=(0, curv_max))
            hist = hist.astype(np.float32)
            total = hist.sum()
            if total > 0:
                hist /= total
        vector_parts.append(hist)

    # Orientation histograms per quadrant (8 bins × 4 = 32)
    for ys, xs in quadrant_slices:
        q_mask = mask[ys, xs]
        q_orient = orientation[ys, xs]
        vals = q_orient[q_mask]
        if len(vals) == 0:
            hist = np.zeros(8, dtype=np.float32)
        else:
            hist, _ = np.histogram(vals, bins=8, range=(-math.pi, math.pi))
            hist = hist.astype(np.float32)
            total = hist.sum()
            if total > 0:
                hist /= total
        vector_parts.append(hist)

    # 4×4 spatial density grid = 16
    cell_h = h // 4
    cell_w = w // 4
    density_grid = np.zeros(16, dtype=np.float32)
    total_edge_pixels = float(mask.sum()) or 1.0
    for gy in range(4):
        for gx in range(4):
            y0 = gy * cell_h
            y1 = (gy + 1) * cell_h if gy < 3 else h
            x0 = gx * cell_w
            x1 = (gx + 1) * cell_w if gx < 3 else w
            count = mask[y0:y1, x0:x1].sum()
            density_grid[gy * 4 + gx] = count / total_edge_pixels
    vector_parts.append(density_grid)

    # Scalar features
    # Parallelism: how much orientations cluster into one direction
    all_orient = orientation[mask]
    if len(all_orient) > 0:
        # Use circular variance: 1 - |mean resultant|
        mean_cos = np.mean(np.cos(2 * all_orient))
        mean_sin = np.mean(np.sin(2 * all_orient))
        resultant = math.sqrt(float(mean_cos) ** 2 + float(mean_sin) ** 2)
        parallelism = float(resultant)
        dominant_orientation_rad = math.atan2(float(mean_sin), float(mean_cos)) / 2
        dominant_orientation_deg = math.degrees(dominant_orientation_rad) % 180
    else:
        parallelism = 0.0
        dominant_orientation_deg = 0.0

    # Edge density: fraction of pixels that are edges
    edge_density = float(mask.sum()) / float(h * w)

    # Vertical centroid: mean y-position of edge pixels normalized to [0, 1]
    ys_all = np.where(mask)[0]
    vertical_centroid = float(np.mean(ys_all) / h) if len(ys_all) > 0 else 0.5

    # Feature scale: approximate by average distance from centroid
    if len(ys_all) > 0:
        xs_all = np.where(mask)[1]
        cy = np.mean(ys_all)
        cx = np.mean(xs_all)
        dists = np.sqrt((ys_all - cy) ** 2 + (xs_all - cx) ** 2)
        feature_scale = float(np.mean(dists)) / (max(h, w) / 2.0)
    else:
        feature_scale = 0.0

    scalar_part = np.array(
        [parallelism, dominant_orientation_deg / 180.0, vertical_centroid, feature_scale],
        dtype=np.float32,
    )
    vector_parts.append(scalar_part)

    vector = np.concatenate(vector_parts)
    assert vector.shape == (_FINGERPRINT_DIM,), f"Expected {_FINGERPRINT_DIM}, got {vector.shape[0]}"

    summary = {
        "dominantOrientationDegrees": round(dominant_orientation_deg, 1),
        "edgeDensity": round(edge_density, 4),
        "parallelism": round(parallelism, 4),
        "verticalCentroid": round(vertical_centroid, 4),
        "featureScale": round(feature_scale, 4),
    }

    return vector, summary


# ── Public API ───────────────────────────────────────────────────────────────


def extract_fingerprint(rgb: np.ndarray) -> dict:
    """Extract structural fingerprint from an RGB image.

    Returns a dict with:
      - ``vector``: np.ndarray of shape (100,)
      - ``summary``: dict with scalar summary fields
      - ``edge_map``: np.ndarray float32 edge map
      - ``skeleton``: np.ndarray float32 skeleton
    """
    edge_map = _run_hed(rgb)
    skeleton = _skeletonize_edges(edge_map)
    curvature = _compute_curvature_at_points(skeleton)
    orientation = _compute_orientation_at_points(skeleton)
    vector, summary = _build_fingerprint_vector(skeleton, curvature, orientation, edge_map)

    return {
        "vector": vector,
        "summary": summary,
        "edge_map": edge_map,
        "skeleton": skeleton,
    }


def extract_fingerprint_from_contours(
    contour_image: np.ndarray,
) -> np.ndarray:
    """Extract fingerprint vector from a binary contour image (for DEM patches).

    The contour image should be a float32 array in [0, 1].
    Returns an np.ndarray of shape (100,).
    """
    skeleton = _skeletonize_edges(contour_image, threshold=0.3)
    curvature = _compute_curvature_at_points(skeleton)
    orientation = _compute_orientation_at_points(skeleton)
    vector, _ = _build_fingerprint_vector(skeleton, curvature, orientation, contour_image)
    return vector
