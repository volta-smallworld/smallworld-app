"""DEM patch matching and style-aware viewpoint generation.

Scans the elevation grid with sliding windows, extracts contour-based
fingerprint descriptors, matches them to the uploaded reference, and
feeds style-boosted scene seeds into the viewpoint generation pipeline.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from smallworld_api.config import settings
from smallworld_api.services.style_fingerprint import extract_fingerprint_from_contours, cosine_similarity
from smallworld_api.services.tiles import GeoBounds
from smallworld_api.services.viewpoints import generate_viewpoints

logger = logging.getLogger(__name__)

_NUM_CONTOUR_LEVELS = 12


# ── Patch extraction ─────────────────────────────────────────────────────────


def _extract_dem_patches(
    dem: np.ndarray,
    window: int,
    stride: int,
) -> list[dict]:
    """Slide a square window across the DEM and return patch metadata."""
    h, w = dem.shape
    patches: list[dict] = []

    for row in range(0, h - window + 1, stride):
        for col in range(0, w - window + 1, stride):
            patch = dem[row : row + window, col : col + window]
            patches.append({
                "row": row,
                "col": col,
                "window": window,
                "patch": patch,
            })

    return patches


def _patch_center_latlng(
    row: int, col: int, window: int, dem_shape: tuple[int, int], bounds: GeoBounds
) -> dict:
    """Convert patch center pixel to lat/lng."""
    h, w = dem_shape
    center_row = row + window / 2
    center_col = col + window / 2
    lat = bounds.north - (center_row / h) * (bounds.north - bounds.south)
    lng = bounds.west + (center_col / w) * (bounds.east - bounds.west)
    return {"lat": float(lat), "lng": float(lng)}


# ── Contour rasterisation ────────────────────────────────────────────────────


def _rasterise_contours(patch: np.ndarray, num_levels: int = _NUM_CONTOUR_LEVELS) -> np.ndarray:
    """Rasterise elevation contours into a binary image.

    Returns a float32 image in [0, 1] of the same size as the patch.
    """
    h, w = patch.shape
    pmin = float(np.min(patch))
    pmax = float(np.max(patch))

    if pmax - pmin < 1.0:
        return np.zeros((h, w), dtype=np.float32)

    # Normalise patch to [0, 255] for OpenCV contour detection
    norm = ((patch - pmin) / (pmax - pmin) * 255).astype(np.uint8)

    canvas = np.zeros((h, w), dtype=np.float32)
    levels = np.linspace(pmin, pmax, num_levels + 2)[1:-1]

    for level in levels:
        threshold = int((level - pmin) / (pmax - pmin) * 255)
        _, binary = cv2.threshold(norm, threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(canvas, contours, -1, 1.0, 1)

    return np.clip(canvas, 0, 1)


# ── Patch descriptors ────────────────────────────────────────────────────────


def _compute_patch_descriptor(patch: np.ndarray) -> dict:
    """Compute contour fingerprint and geometric metadata for a DEM patch."""
    contour_img = _rasterise_contours(patch)
    fingerprint = extract_fingerprint_from_contours(contour_img)

    # Average surface normal (slope direction)
    dy, dx = np.gradient(patch)
    mean_dx = float(np.mean(dx))
    mean_dy = float(np.mean(dy))
    normal_angle = math.degrees(math.atan2(mean_dy, mean_dx))

    # Dominant contour direction (from fingerprint orientation histogram)
    # This is already encoded in the fingerprint vector

    # Feature scale: std of elevation normalised by patch size
    elev_range = float(np.max(patch)) - float(np.min(patch))
    feature_scale = elev_range / max(patch.shape)

    return {
        "fingerprint": fingerprint,
        "contour_image": contour_img,
        "surface_normal_degrees": normal_angle,
        "mean_slope_dx": mean_dx,
        "mean_slope_dy": mean_dy,
        "feature_scale": feature_scale,
        "elevation_range": elev_range,
    }


# ── Scene synthesis ──────────────────────────────────────────────────────────


def _find_overlapping_scene(
    patch_center: dict,
    scenes: list[dict],
    threshold_meters: float = 500.0,
) -> str | None:
    """Find an existing scene within threshold of the patch center."""
    for scene in scenes:
        sc = scene.get("center", {})
        dlat = patch_center["lat"] - sc.get("lat", 0)
        dlng = patch_center["lng"] - sc.get("lng", 0)
        lat_rad = math.radians((patch_center["lat"] + sc.get("lat", 0)) / 2)
        dist = math.sqrt((dlat * 111320) ** 2 + (dlng * 111320 * math.cos(lat_rad)) ** 2)
        if dist < threshold_meters:
            return scene.get("id")
    return None


def _find_nearby_features(
    patch_center: dict,
    all_features: dict[str, list[dict]],
    radius_meters: float = 500.0,
) -> list[str]:
    """Find feature IDs near the patch center."""
    feature_ids: list[str] = []
    for feat_type, feats in all_features.items():
        for feat in feats:
            if "center" in feat:
                fc = feat["center"]
            elif "path" in feat and feat["path"]:
                mid = feat["path"][len(feat["path"]) // 2]
                fc = {"lat": mid["lat"], "lng": mid["lng"]}
            else:
                continue

            dlat = patch_center["lat"] - fc["lat"]
            dlng = patch_center["lng"] - fc["lng"]
            lat_rad = math.radians((patch_center["lat"] + fc["lat"]) / 2)
            dist = math.sqrt((dlat * 111320) ** 2 + (dlng * 111320 * math.cos(lat_rad)) ** 2)
            if dist < radius_meters:
                feature_ids.append(feat.get("id", ""))
    return [fid for fid in feature_ids if fid]


# ── Contour-based gradient refinement ────────────────────────────────────────


def _refine_style_candidate(
    candidate: dict,
    reference_fingerprint: np.ndarray,
    dem: np.ndarray,
    bounds: GeoBounds,
    patch_descriptor: dict,
) -> dict:
    """Refine camera parameters using numerical gradient ascent.

    Adjusts east offset, north offset, altitude offset, heading, pitch
    to maximise contour similarity with the reference.
    """
    max_iterations = settings.style_refinement_iterations
    lr = settings.style_refinement_learning_rate
    eps = 1e-4

    cam = candidate["camera"]
    params = [
        cam["lat"],
        cam["lng"],
        cam["altitudeMeters"],
        cam["headingDegrees"],
        cam["pitchDegrees"],
    ]

    # Bounds for refinement
    lat_range = 250.0 / 111320  # ±250m in lat degrees
    lng_range = 250.0 / (111320 * math.cos(math.radians(cam["lat"])))
    bounds_low = [
        cam["lat"] - lat_range,
        cam["lng"] - lng_range,
        cam["altitudeMeters"] - 80,
        cam["headingDegrees"] - 12,
        cam["pitchDegrees"] - 8,
    ]
    bounds_high = [
        cam["lat"] + lat_range,
        cam["lng"] + lng_range,
        cam["altitudeMeters"] + 80,
        cam["headingDegrees"] + 12,
        cam["pitchDegrees"] + 8,
    ]

    best_score = patch_descriptor.get("similarity", 0.0)
    best_params = list(params)

    for iteration in range(max_iterations):
        # Compute gradient via central differences
        gradient = [0.0] * 5
        step_sizes = [lat_range * 0.05, lng_range * 0.05, 4.0, 1.0, 0.5]

        current_score = best_score

        for dim in range(5):
            p_plus = list(best_params)
            p_minus = list(best_params)
            p_plus[dim] = min(best_params[dim] + step_sizes[dim], bounds_high[dim])
            p_minus[dim] = max(best_params[dim] - step_sizes[dim], bounds_low[dim])

            # Score is based on how well the viewpoint "sees" the patch
            # Simplified: use angular alignment with patch surface normal
            score_plus = _score_viewpoint_style(p_plus, patch_descriptor, reference_fingerprint)
            score_minus = _score_viewpoint_style(p_minus, patch_descriptor, reference_fingerprint)

            gradient[dim] = (score_plus - score_minus) / (2 * step_sizes[dim] + 1e-10)

        # Update parameters
        new_params = list(best_params)
        for dim in range(5):
            new_params[dim] = best_params[dim] + lr * gradient[dim] * step_sizes[dim]
            new_params[dim] = max(bounds_low[dim], min(bounds_high[dim], new_params[dim]))

        new_score = _score_viewpoint_style(new_params, patch_descriptor, reference_fingerprint)

        if new_score > best_score + eps:
            best_score = new_score
            best_params = new_params
        else:
            break

    # Update candidate with refined parameters
    candidate["camera"]["lat"] = round(best_params[0], 6)
    candidate["camera"]["lng"] = round(best_params[1], 6)
    candidate["camera"]["altitudeMeters"] = round(best_params[2], 1)
    candidate["camera"]["headingDegrees"] = round(best_params[3] % 360, 1)
    candidate["camera"]["pitchDegrees"] = round(best_params[4], 1)
    candidate["_contour_refinement"] = round(best_score, 4)

    return candidate


def _score_viewpoint_style(
    params: list[float],
    patch_descriptor: dict,
    reference_fingerprint: np.ndarray,
) -> float:
    """Score a viewpoint parametrisation for style similarity.

    Combines fingerprint cosine similarity with angular alignment.
    """
    cam_lat, cam_lng, cam_alt, heading, pitch = params

    # Base fingerprint similarity
    fp_sim = cosine_similarity(patch_descriptor["fingerprint"], reference_fingerprint)

    # Angular alignment: heading toward patch should align with
    # the negative surface normal (viewing from outside)
    normal_angle = patch_descriptor.get("surface_normal_degrees", 0.0)
    heading_alignment = 1.0 - abs(_heading_delta(heading, normal_angle + 180)) / 180.0

    return 0.7 * fp_sim + 0.3 * heading_alignment


def _heading_delta(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


# ── Main orchestrator ────────────────────────────────────────────────────────


def find_style_viewpoints(
    dem: np.ndarray,
    bounds: GeoBounds,
    cell_size_meters: float,
    scenes: list[dict],
    all_features: dict[str, list[dict]],
    interest_raster: np.ndarray,
    compositions: list[str],
    reference_fingerprint: np.ndarray,
    reference_metadata: dict,
    max_viewpoints: int = 12,
    max_per_scene: int = 3,
    top_patch_count: int = 24,
) -> dict:
    """Generate style-aware viewpoints by matching DEM patches to reference.

    Returns a dict with ``viewpoints`` and ``summary``.
    """
    window = settings.style_patch_window_cells
    stride = settings.style_patch_stride_cells

    # 1. Extract and score DEM patches
    raw_patches = _extract_dem_patches(dem, window, stride)
    patches_scanned = len(raw_patches)

    scored_patches: list[dict] = []
    for p in raw_patches:
        descriptor = _compute_patch_descriptor(p["patch"])
        similarity = cosine_similarity(descriptor["fingerprint"], reference_fingerprint)
        center = _patch_center_latlng(p["row"], p["col"], p["window"], dem.shape, bounds)

        nearby_features = _find_nearby_features(center, all_features)

        scored_patches.append({
            **p,
            "descriptor": descriptor,
            "similarity": similarity,
            "center": center,
            "feature_ids": nearby_features,
        })

    # 2. Keep top N patches
    scored_patches.sort(key=lambda x: -x["similarity"])
    top_patches = scored_patches[:top_patch_count]
    style_patch_matches = len(top_patches)

    # 3. Attach patches to scenes or synthesize new scene seeds
    augmented_scenes = list(scenes)
    patch_scene_map: dict[int, str] = {}

    for i, patch in enumerate(top_patches):
        existing_scene_id = _find_overlapping_scene(patch["center"], augmented_scenes)
        if existing_scene_id:
            patch_scene_map[i] = existing_scene_id
        else:
            synthetic_id = f"style-patch-{i + 1}"
            synthetic_scene = {
                "id": synthetic_id,
                "type": "style-patch",
                "center": patch["center"],
                "featureIds": patch["feature_ids"],
                "summary": f"Style-matched patch (similarity={patch['similarity']:.2f})",
                "score": patch["similarity"],
            }
            augmented_scenes.append(synthetic_scene)
            patch_scene_map[i] = synthetic_id

    # 4. Generate viewpoints using the standard pipeline with augmented scenes
    vp_result = generate_viewpoints(
        dem=dem,
        bounds=bounds,
        cell_size_meters=cell_size_meters,
        scenes=augmented_scenes,
        all_features=all_features,
        interest_raster=interest_raster,
        compositions=compositions,
        max_viewpoints=max_viewpoints * 2,  # generate more, then re-rank
        max_per_scene=max_per_scene,
    )

    base_viewpoints = vp_result["viewpoints"]
    base_summary = vp_result["summary"]

    # 5. Build a mapping: scene_id -> best matching patch
    scene_to_patch: dict[str, dict] = {}
    for i, patch in enumerate(top_patches):
        sid = patch_scene_map.get(i)
        if sid and sid not in scene_to_patch:
            scene_to_patch[sid] = patch

    # 6. Augment viewpoints with style metadata and re-score
    style_viewpoints: list[dict] = []
    for vp in base_viewpoints:
        scene_id = vp.get("sceneId", "")
        patch = scene_to_patch.get(scene_id)

        if patch is None:
            # No style patch for this scene — use zero style scores
            patch_similarity = 0.0
            contour_refinement = 0.0
            matched_feature_ids: list[str] = []
            patch_id = "none"
        else:
            patch_similarity = patch["similarity"]
            matched_feature_ids = patch.get("feature_ids", [])
            patch_id = f"style-patch-{top_patches.index(patch) + 1}" if patch in top_patches else "none"

            # Refine the candidate
            _refine_style_candidate(vp, reference_fingerprint, dem, bounds, patch["descriptor"])
            contour_refinement = vp.pop("_contour_refinement", patch_similarity)

        base_score = vp.get("score", 0.0)

        # Pre-render style score formula
        pre_render_score = (
            0.45 * contour_refinement
            + 0.35 * patch_similarity
            + 0.20 * base_score
        )

        style_vp = {
            **vp,
            "baseScore": round(base_score, 4),
            "score": round(pre_render_score, 4),
            "style": {
                "patchId": patch_id,
                "matchedFeatureIds": matched_feature_ids,
                "geometrySimilarity": round(patch_similarity, 4),
                "patchSimilarity": round(patch_similarity, 4),
                "contourRefinement": round(contour_refinement, 4),
                "preRenderScore": round(pre_render_score, 4),
                "verificationStatus": "pending",
                "clipSimilarity": None,
                "lpipsDistance": None,
                "edgeSimilarity": None,
                "finalStyleScore": None,
            },
        }
        style_viewpoints.append(style_vp)

    # 7. Sort by pre-render score
    style_viewpoints.sort(key=lambda x: -x["score"])

    # 8. Enforce limits
    scene_counts: dict[str, int] = {}
    limited: list[dict] = []
    for vp in style_viewpoints:
        sid = vp["sceneId"]
        count = scene_counts.get(sid, 0)
        if count >= max_per_scene:
            continue
        scene_counts[sid] = count + 1
        limited.append(vp)

    limited = limited[:max_viewpoints]

    # 9. Re-assign IDs
    for i, vp in enumerate(limited):
        vp["id"] = f"vp-{i + 1}"

    # 10. Build style-specific summary
    style_candidates_refined = sum(
        1 for vp in limited if vp["style"]["patchId"] != "none"
    )

    summary = {
        "sceneCount": base_summary.get("sceneCount", 0),
        "eligibleSceneCount": base_summary.get("eligibleSceneCount", 0),
        "candidatesGenerated": base_summary.get("candidatesGenerated", 0),
        "candidatesRejected": base_summary.get("candidatesRejected", {}),
        "patchesScanned": patches_scanned,
        "stylePatchMatches": style_patch_matches,
        "styleCandidatesRefined": style_candidates_refined,
        "returned": len(limited),
    }

    return {
        "viewpoints": limited,
        "summary": summary,
    }
