"""Viewpoint generation orchestrator.

Ties together camera geometry, fractal analysis, composition templates,
and visibility scoring to produce ranked viewpoints for terrain scenes.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import least_squares

from smallworld_api.services.camera_geometry import (
    bilinear_elevation,
    check_line_of_sight,
    compute_heading,
    enu_to_latlng,
    latlng_to_enu,
    pitch_from_horizon_ratio,
    project_to_image,
)
from smallworld_api.services.composition_templates import (
    CompositionTemplate,
    get_eligible_templates,
    select_anchors,
)
from smallworld_api.services.fractals import (
    fallback_viewing_distance,
    preferred_viewing_distance,
)
from smallworld_api.services.tiles import GeoBounds

# Feature type categories
_POINT_FEATURE_TYPES = ("peak", "cliff")
_LINE_FEATURE_TYPES = ("ridge", "water")

# PnP solver types that use scipy least_squares
_PNP_SOLVER_TYPES = ("pnp",)
_LEADING_LINE_SOLVER_TYPES = ("leading_line",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _distance_approx(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate distance in meters between two lat/lng points."""
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    lat_rad = math.radians((lat1 + lat2) / 2)
    return math.sqrt((dlat * 111320) ** 2 + (dlng * 111320 * math.cos(lat_rad)) ** 2)


def _feature_center(feat: dict) -> dict:
    """Return the center lat/lng of a feature (point or line)."""
    if "center" in feat:
        return feat["center"]
    # Line feature — use midpoint of path
    path = feat.get("path", [])
    if path:
        mid = path[len(path) // 2]
        return {"lat": mid["lat"], "lng": mid["lng"]}
    return {"lat": 0.0, "lng": 0.0}


def _is_point_feature(feat: dict) -> bool:
    """Check whether a feature is a point type based on its id prefix."""
    fid = feat.get("id", "")
    return any(fid.startswith(f"{t}-") for t in _POINT_FEATURE_TYPES)


def _is_line_feature(feat: dict) -> bool:
    """Check whether a feature is a line type based on its id prefix."""
    fid = feat.get("id", "")
    return any(fid.startswith(f"{t}-") for t in _LINE_FEATURE_TYPES)


def _heading_delta(a: float, b: float) -> float:
    """Absolute angular difference between two headings in degrees."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _feature_sort_key(feat: dict) -> tuple:
    """Sort key: score descending, then id ascending."""
    return (-feat.get("score", 0.0), feat.get("id", ""))


# ---------------------------------------------------------------------------
# Scene context builder
# ---------------------------------------------------------------------------


def _build_scene_context(
    scene: dict,
    feature_index: dict[str, dict],
) -> dict:
    """Build context for a single scene: features, extent, relief."""
    features = [feature_index[fid] for fid in scene.get("featureIds", []) if fid in feature_index]

    points = sorted([f for f in features if _is_point_feature(f)], key=_feature_sort_key)
    lines = sorted([f for f in features if _is_line_feature(f)], key=_feature_sort_key)

    # Compute scene extent: max distance between any two feature centers
    all_centers = [_feature_center(f) for f in features]
    scene_extent_meters = 0.0
    for i in range(len(all_centers)):
        for j in range(i + 1, len(all_centers)):
            d = _distance_approx(
                all_centers[i]["lat"],
                all_centers[i]["lng"],
                all_centers[j]["lat"],
                all_centers[j]["lng"],
            )
            scene_extent_meters = max(scene_extent_meters, d)

    # Compute scene relief: max elevation - min elevation of point features
    point_elevations = [
        f.get("elevationMeters", 0.0) for f in points if "elevationMeters" in f
    ]
    scene_relief_meters = 0.0
    if point_elevations:
        scene_relief_meters = max(point_elevations) - min(point_elevations)

    return {
        "scene": scene,
        "points": points,
        "lines": lines,
        "scene_features": {"points": points, "lines": lines},
        "scene_extent_meters": scene_extent_meters,
        "scene_relief_meters": scene_relief_meters,
    }


# ---------------------------------------------------------------------------
# Anchor position helpers
# ---------------------------------------------------------------------------


def _anchor_3d_position(
    feat: dict,
    dem: np.ndarray,
    bounds: GeoBounds,
    origin_lat: float,
    origin_lng: float,
) -> tuple[float, float, float]:
    """Get (east, north, altitude) for an anchor feature in ENU coordinates."""
    center = _feature_center(feat)
    lat, lng = center["lat"], center["lng"]
    east, north = latlng_to_enu(lat, lng, origin_lat, origin_lng)
    alt = bilinear_elevation(dem, bounds, lat, lng)
    return (east, north, alt)


# ---------------------------------------------------------------------------
# PnP solver
# ---------------------------------------------------------------------------


def _solve_pnp(
    template: CompositionTemplate,
    anchors: dict[str, dict],
    dem: np.ndarray,
    bounds: GeoBounds,
    scene: dict,
    viewing_distance: float,
    scene_relief: float,
    fov_degrees: float,
) -> dict | None:
    """Solve camera pose using scipy least_squares for PnP-type templates.

    Returns a dict with cam_lat, cam_lng, cam_alt, heading_deg, pitch_deg
    or None if the solver fails.
    """
    origin_lat = scene["center"]["lat"]
    origin_lng = scene["center"]["lng"]

    # Build anchor positions and target placements
    anchor_positions: list[tuple[float, float, float]] = []
    target_placements: list[tuple[float, float]] = []

    for target in template.targets:
        role = target.role
        if role not in anchors:
            return None
        feat = anchors[role]
        pos = _anchor_3d_position(feat, dem, bounds, origin_lat, origin_lng)
        anchor_positions.append(pos)
        target_placements.append((target.xNorm, target.yNorm))

    if not anchor_positions:
        return None

    # Compute pitch from template horizon ratio
    pitch_deg = pitch_from_horizon_ratio(template.horizon_ratio, fov_degrees)

    # Compute midpoint of anchors in ENU
    mid_e = sum(p[0] for p in anchor_positions) / len(anchor_positions)
    mid_n = sum(p[1] for p in anchor_positions) / len(anchor_positions)

    # Initial camera guess: place opposite the primary anchor
    primary_e, primary_n, _ = anchor_positions[0]
    offset_e = mid_e - primary_e
    offset_n = mid_n - primary_n
    offset_len = math.sqrt(offset_e**2 + offset_n**2) or 1.0
    cam_e_init = mid_e + offset_e / offset_len * viewing_distance
    cam_n_init = mid_n + offset_n / offset_len * viewing_distance
    max_anchor_alt = max(alt for _, _, alt in anchor_positions)
    cam_alt_init = max_anchor_alt + max(30.0, scene_relief * 0.15)
    yaw_init = compute_heading(cam_e_init, cam_n_init, mid_e, mid_n)

    def residuals(params: list[float]) -> list[float]:
        cam_e, cam_n, cam_z, yaw = params
        res: list[float] = []
        for (ae, an, aa), (tx, ty) in zip(anchor_positions, target_placements):
            projected = project_to_image(
                (ae, an, aa), (cam_e, cam_n), cam_z, yaw, pitch_deg, fov_degrees
            )
            if projected is None:
                res.extend([1.0, 1.0])
            else:
                res.append(projected[0] - tx)
                res.append(projected[1] - ty)
        return res

    result = least_squares(
        residuals,
        [cam_e_init, cam_n_init, cam_alt_init, yaw_init],
        method="lm",
    )

    if not result.success:
        return None

    rms = math.sqrt(sum(r**2 for r in result.fun) / len(result.fun))
    if rms > 0.08:
        return None

    cam_e, cam_n, cam_alt, heading_deg = result.x
    cam_lat, cam_lng = enu_to_latlng(cam_e, cam_n, origin_lat, origin_lng)

    return {
        "cam_lat": cam_lat,
        "cam_lng": cam_lng,
        "cam_alt": float(cam_alt),
        "heading_deg": float(heading_deg) % 360,
        "pitch_deg": pitch_deg,
        "anchor_positions": anchor_positions,
        "target_placements": target_placements,
        "origin_lat": origin_lat,
        "origin_lng": origin_lng,
    }


# ---------------------------------------------------------------------------
# Leading line solver
# ---------------------------------------------------------------------------


def _solve_leading_line(
    template: CompositionTemplate,
    anchors: dict[str, dict],
    dem: np.ndarray,
    bounds: GeoBounds,
    scene: dict,
    viewing_distance: float,
    scene_relief: float,
    fov_degrees: float,
) -> dict | None:
    """Constructive solver for leading-line compositions.

    Returns a dict with cam_lat, cam_lng, cam_alt, heading_deg, pitch_deg
    or None if the solver fails.
    """
    line_feat = anchors.get("line")
    subject_feat = anchors.get("subject")
    if line_feat is None or subject_feat is None:
        return None

    path = line_feat.get("path", [])
    if len(path) < 2:
        return None

    origin_lat = scene["center"]["lat"]
    origin_lng = scene["center"]["lng"]

    # Use first third of the path
    idx = max(0, len(path) // 3 - 1)
    line_start = path[0]
    line_end = path[-1]

    # Determine entry direction
    start_e, start_n = latlng_to_enu(line_start["lat"], line_start["lng"], origin_lat, origin_lng)
    end_e, end_n = latlng_to_enu(line_end["lat"], line_end["lng"], origin_lat, origin_lng)

    # Place camera behind the first third of the line
    entry_pt = path[idx]
    entry_e, entry_n = latlng_to_enu(entry_pt["lat"], entry_pt["lng"], origin_lat, origin_lng)

    # Line tangent direction
    tangent_e = end_e - start_e
    tangent_n = end_n - start_n
    tangent_len = math.sqrt(tangent_e**2 + tangent_n**2) or 1.0

    # Camera behind the entry point (opposite tangent direction)
    cam_e = entry_e - (tangent_e / tangent_len) * viewing_distance
    cam_n = entry_n - (tangent_n / tangent_len) * viewing_distance
    cam_lat, cam_lng = enu_to_latlng(cam_e, cam_n, origin_lat, origin_lng)

    # Altitude
    ground_elev = bilinear_elevation(dem, bounds, cam_lat, cam_lng)
    cam_alt = ground_elev + max(10.0, scene_relief * 0.08)

    # Heading toward subject
    subject_center = subject_feat["center"]
    subject_e, subject_n = latlng_to_enu(
        subject_center["lat"], subject_center["lng"], origin_lat, origin_lng
    )
    heading_deg = compute_heading(cam_e, cam_n, subject_e, subject_n)
    pitch_deg = pitch_from_horizon_ratio(template.horizon_ratio, fov_degrees)

    # Build anchor positions for validation
    anchor_positions = [
        _anchor_3d_position(subject_feat, dem, bounds, origin_lat, origin_lng),
    ]
    target_placements = [(template.targets[0].xNorm, template.targets[0].yNorm)]

    return {
        "cam_lat": cam_lat,
        "cam_lng": cam_lng,
        "cam_alt": cam_alt,
        "heading_deg": heading_deg % 360,
        "pitch_deg": pitch_deg,
        "anchor_positions": anchor_positions,
        "target_placements": target_placements,
        "origin_lat": origin_lat,
        "origin_lng": origin_lng,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_candidate(
    pose: dict,
    dem: np.ndarray,
    bounds: GeoBounds,
    min_clearance: float,
    rejections: dict[str, int],
) -> bool:
    """Run validation checks on a candidate pose. Returns True if valid."""
    cam_lat = pose["cam_lat"]
    cam_lng = pose["cam_lng"]
    cam_alt = pose["cam_alt"]

    # Out of bounds check
    if not (bounds.south <= cam_lat <= bounds.north and bounds.west <= cam_lng <= bounds.east):
        rejections["outOfBounds"] = rejections.get("outOfBounds", 0) + 1
        return False

    # Ground clearance check
    ground_elev = bilinear_elevation(dem, bounds, cam_lat, cam_lng)
    clearance = cam_alt - ground_elev
    if clearance < min_clearance:
        rejections["underground"] = rejections.get("underground", 0) + 1
        return False

    return True


def _check_anchor_visibility(
    pose: dict,
    dem: np.ndarray,
    bounds: GeoBounds,
    anchors: dict[str, dict],
    template: CompositionTemplate,
    rejections: dict[str, int],
) -> list[dict] | None:
    """Check line-of-sight to each anchor and build targets list.

    Returns a list of target dicts with visibility info, or None if no
    required targets are visible.
    """
    cam_lat = pose["cam_lat"]
    cam_lng = pose["cam_lng"]
    cam_alt = pose["cam_alt"]
    heading_deg = pose["heading_deg"]
    pitch_deg = pose["pitch_deg"]
    fov_degrees = 55.0  # Will be overridden by caller if needed
    anchor_positions = pose["anchor_positions"]
    target_placements = pose["target_placements"]
    origin_lat = pose["origin_lat"]
    origin_lng = pose["origin_lng"]

    visible_targets: list[dict] = []
    any_visible = False

    roles = [t.role for t in template.targets]

    for i, (role, (ae, an, aa), (tx, ty)) in enumerate(
        zip(roles, anchor_positions, target_placements)
    ):
        if role not in anchors:
            continue
        feat = anchors[role]
        center = _feature_center(feat)

        is_visible = check_line_of_sight(
            dem, bounds, cam_lat, cam_lng, cam_alt, center["lat"], center["lng"], aa
        )

        if is_visible:
            any_visible = True

        visible_targets.append(
            {
                "role": role,
                "featureId": feat.get("id", ""),
                "visible": is_visible,
                "xNorm": tx,
                "yNorm": ty,
            }
        )

    if not any_visible:
        rejections["occluded"] = rejections.get("occluded", 0) + 1
        return None

    return visible_targets


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _deduplicate(
    candidates: list[dict],
    dedup_distance: float,
    dedup_heading: float,
) -> list[dict]:
    """Remove duplicate candidates (same scene, same composition, similar pose)."""
    kept: list[dict] = []
    for cand in candidates:
        is_dup = False
        for existing in kept:
            if (
                cand["sceneId"] == existing["sceneId"]
                and cand["composition"] == existing["composition"]
            ):
                sep = _distance_approx(
                    cand["camera"]["lat"],
                    cand["camera"]["lng"],
                    existing["camera"]["lat"],
                    existing["camera"]["lng"],
                )
                hdelta = _heading_delta(cand["camera"]["headingDegrees"], existing["camera"]["headingDegrees"])
                if sep < dedup_distance and hdelta < dedup_heading:
                    is_dup = True
                    # Keep higher score — existing is already in kept
                    break
        if not is_dup:
            kept.append(cand)
    return kept


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def generate_viewpoints(
    dem: np.ndarray,
    bounds: GeoBounds,
    cell_size_meters: float,
    scenes: list[dict],
    all_features: dict[str, list[dict]],
    interest_raster: np.ndarray,
    compositions: list[str],
    max_viewpoints: int = 12,
    max_per_scene: int = 3,
    fov_degrees: float = 55,
    min_clearance: float = 2,
    dedup_distance: float = 150,
    dedup_heading: float = 12,
) -> dict:
    """Generate ranked viewpoints for terrain scenes.

    Parameters
    ----------
    dem : np.ndarray
        128x128 elevation grid in meters.
    bounds : GeoBounds
        Geographic bounds of the DEM.
    cell_size_meters : float
        Approximate size of a DEM cell in meters.
    scenes : list[dict]
        Scene dicts with id, type, center, featureIds, summary, score.
    all_features : dict[str, list[dict]]
        Mapping of feature type name to list of feature dicts.
        Keys like "peaks", "ridges", "cliffs", "waterChannels".
    interest_raster : np.ndarray
        128x128 interest surface in [0, 1].
    compositions : list[str]
        Requested composition types (e.g. ["ruleOfThirds", "goldenRatio"]).
    max_viewpoints : int
        Maximum total viewpoints to return.
    max_per_scene : int
        Maximum viewpoints per scene.
    fov_degrees : float
        Camera horizontal field of view in degrees.
    min_clearance : float
        Minimum camera height above terrain in meters.
    dedup_distance : float
        Camera separation threshold for deduplication in meters.
    dedup_heading : float
        Heading difference threshold for deduplication in degrees.

    Returns
    -------
    dict
        ``{"viewpoints": [...], "summary": {...}}``
    """
    # ------------------------------------------------------------------
    # 1. Build feature index
    # ------------------------------------------------------------------
    feature_index: dict[str, dict] = {}
    for _feat_type, feat_list in all_features.items():
        for feat in feat_list:
            fid = feat.get("id")
            if fid:
                feature_index[fid] = feat

    # ------------------------------------------------------------------
    # 2. Collect water channel points
    # ------------------------------------------------------------------
    water_channel_points: list[dict] = []
    for wc in all_features.get("waterChannels", []):
        for pt in wc.get("path", []):
            water_channel_points.append({"lat": pt["lat"], "lng": pt["lng"]})

    # ------------------------------------------------------------------
    # Rejection counters
    # ------------------------------------------------------------------
    rejections: dict[str, int] = {
        "templateIneligible": 0,
        "noConvergence": 0,
        "outOfBounds": 0,
        "underground": 0,
        "occluded": 0,
    }

    candidates: list[dict] = []
    total_scenes = len(scenes)
    eligible_scene_count = 0

    # ------------------------------------------------------------------
    # 3 & 4 & 5. For each scene, build context, get templates, solve
    # ------------------------------------------------------------------
    for scene in scenes:
        ctx = _build_scene_context(scene, feature_index)
        scene_features = ctx["scene_features"]
        scene_extent = ctx["scene_extent_meters"]
        scene_relief = ctx["scene_relief_meters"]

        # 4. Get eligible templates
        templates = get_eligible_templates(scene.get("type", ""), compositions)
        if templates:
            eligible_scene_count += 1

        for template in templates:
            # 5a. Select anchors
            anchors = select_anchors(scene_features, template)
            if anchors is None:
                rejections["templateIneligible"] += 1
                continue

            # 5b. Determine anchor 3D positions (done inside solvers)

            # 5c. Compute preferred viewing distance
            ridges_in_lines = [
                ln for ln in ctx["lines"] if ln.get("id", "").startswith("ridge-")
            ]
            if ridges_in_lines:
                top_ridge = ridges_in_lines[0]
                viewing_distance = preferred_viewing_distance(
                    top_ridge["path"], dem, bounds, cell_size_meters, fov_degrees
                )
            else:
                viewing_distance = fallback_viewing_distance(scene_extent)

            # 5d. Solve camera pose
            pose: dict | None = None
            if template.solver_type == "leading_line":
                pose = _solve_leading_line(
                    template,
                    anchors,
                    dem,
                    bounds,
                    scene,
                    viewing_distance,
                    scene_relief,
                    fov_degrees,
                )
                if pose is None:
                    rejections["noConvergence"] += 1
                    continue
            else:
                # PnP solver (ruleOfThirds, goldenRatio, symmetry)
                pose = _solve_pnp(
                    template,
                    anchors,
                    dem,
                    bounds,
                    scene,
                    viewing_distance,
                    scene_relief,
                    fov_degrees,
                )
                if pose is None:
                    rejections["noConvergence"] += 1
                    continue

            # ----------------------------------------------------------
            # 6. Validate candidate
            # ----------------------------------------------------------
            if not _validate_candidate(pose, dem, bounds, min_clearance, rejections):
                continue

            # Line-of-sight check
            visible_targets = _check_anchor_visibility(
                pose, dem, bounds, anchors, template, rejections
            )
            if visible_targets is None:
                continue

            # ----------------------------------------------------------
            # 7. Build candidate dict
            # ----------------------------------------------------------
            cam_lat = pose["cam_lat"]
            cam_lng = pose["cam_lng"]
            cam_alt = pose["cam_alt"]
            heading_deg = pose["heading_deg"]
            pitch_deg = pose["pitch_deg"]

            # Build targets from visible_targets
            targets_out = [
                {
                    "featureId": vt["featureId"],
                    "role": vt["role"],
                    "xNorm": vt["xNorm"],
                    "yNorm": vt["yNorm"],
                }
                for vt in visible_targets
            ]

            # Build validation
            ground_elev = bilinear_elevation(dem, bounds, cam_lat, cam_lng)
            clearance = cam_alt - ground_elev
            visible_ids = [vt["featureId"] for vt in visible_targets if vt["visible"]]
            validation = {
                "clearanceMeters": round(clearance, 1),
                "visibleTargetIds": visible_ids,
            }

            # Distance to scene center
            scene_center = scene.get("center", {})
            dist_to_scene = _distance_approx(
                cam_lat, cam_lng, scene_center.get("lat", 0), scene_center.get("lng", 0)
            )

            candidate = {
                "id": "",  # assigned later
                "sceneId": scene.get("id", ""),
                "sceneType": scene.get("type", ""),
                "composition": template.composition,
                "camera": {
                    "lat": round(cam_lat, 6),
                    "lng": round(cam_lng, 6),
                    "altitudeMeters": round(cam_alt, 1),
                    "headingDegrees": round(heading_deg, 1),
                    "pitchDegrees": round(pitch_deg, 1),
                    "rollDegrees": 0,
                    "fovDegrees": fov_degrees,
                },
                "targets": targets_out,
                "distanceMetersApprox": round(dist_to_scene, 1),
                "validation": validation,
                "score": 0.0,  # filled in step 9
                "scoreBreakdown": {},
                "_sceneScore": scene.get("score", 0.0),
            }
            candidates.append(candidate)

    # ------------------------------------------------------------------
    # 8. Score each candidate
    # ------------------------------------------------------------------
    from smallworld_api.services.visibility import score_viewpoint

    for cand in candidates:
        cam = cand["camera"]
        score_result = score_viewpoint(
            dem,
            bounds,
            interest_raster,
            cam["lat"],
            cam["lng"],
            cam["altitudeMeters"],
            cam["fovDegrees"],
            cam["headingDegrees"],
            water_channel_points,
        )
        cand["score"] = round(score_result.get("total", 0.0), 4)
        cand["scoreBreakdown"] = {
            k: round(v, 4) for k, v in score_result.items() if k != "total"
        }

    # Pre-sort by score so dedup keeps the best candidate
    candidates.sort(key=lambda c: -c["score"])

    # Track pre-dedup count for metrics
    pre_dedup_count = len(candidates)

    # ------------------------------------------------------------------
    # 9. Deduplicate
    # ------------------------------------------------------------------
    candidates = _deduplicate(candidates, dedup_distance, dedup_heading)

    # ------------------------------------------------------------------
    # 10. Sort by score desc, then scene score desc, then id asc
    # ------------------------------------------------------------------
    candidates.sort(
        key=lambda c: (-c["score"], -c.get("_sceneScore", 0.0), c.get("sceneId", ""))
    )

    # ------------------------------------------------------------------
    # 11. Enforce limits: max_per_scene, then max_viewpoints
    # ------------------------------------------------------------------
    scene_counts: dict[str, int] = {}
    limited: list[dict] = []
    for cand in candidates:
        sid = cand["sceneId"]
        count = scene_counts.get(sid, 0)
        if count >= max_per_scene:
            continue
        scene_counts[sid] = count + 1
        limited.append(cand)

    limited = limited[:max_viewpoints]

    # ------------------------------------------------------------------
    # 12. Assign IDs
    # ------------------------------------------------------------------
    for i, cand in enumerate(limited):
        cand["id"] = f"vp-{i + 1}"

    # ------------------------------------------------------------------
    # 13. Strip internal fields and return
    # ------------------------------------------------------------------
    for vp in limited:
        vp.pop("_sceneScore", None)

    candidates_generated = pre_dedup_count + sum(rejections.values())

    return {
        "viewpoints": limited,
        "summary": {
            "sceneCount": total_scenes,
            "eligibleSceneCount": eligible_scene_count,
            "candidatesGenerated": candidates_generated,
            "candidatesRejected": rejections,
            "returned": len(limited),
        },
    }
