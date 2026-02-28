"""Adapters between internal viewpoint data and MCP schemas.

Maps camelCase REST viewpoint structures to snake_case MCP schemas,
and constructs preview_input payloads from viewpoint + scene context.
"""

from __future__ import annotations

from smallworld_api.mcp.schemas import (
    McpCameraPose,
    McpCompositionType,
    McpGeoPosition,
    McpPreviewAnchor,
    McpPreviewComposition,
    McpPreviewInput,
    McpPreviewScene,
    McpScoreBreakdown,
    McpValidation,
    McpViewpoint,
    McpViewpointTarget,
    McpViewpointsSummary,
    McpViewpointsRequest,
    composition_to_mcp,
)


def _convert_score_breakdown(breakdown: dict) -> McpScoreBreakdown:
    """Convert camelCase score breakdown to snake_case."""
    return McpScoreBreakdown(
        viewshed_richness=breakdown.get("viewshedRichness", 0.0),
        terrain_entropy=breakdown.get("terrainEntropy", 0.0),
        skyline_fractal=breakdown.get("skylineFractal", 0.0),
        prospect_refuge=breakdown.get("prospectRefuge", 0.0),
        depth_layering=breakdown.get("depthLayering", 0.0),
        mystery=breakdown.get("mystery", 0.0),
        water_visibility=breakdown.get("waterVisibility", 0.0),
    )


def _convert_camera(cam: dict) -> McpCameraPose:
    """Convert camelCase camera dict to MCP camera pose."""
    return McpCameraPose(
        position=McpGeoPosition(
            lat=cam["lat"],
            lng=cam["lng"],
            alt_meters=cam["altitudeMeters"],
        ),
        heading_deg=cam["headingDegrees"],
        pitch_deg=cam["pitchDegrees"],
        roll_deg=cam.get("rollDegrees", 0.0),
        fov_deg=cam.get("fovDegrees", 55.0),
    )


def _build_preview_anchors(
    vp: dict,
    feature_index: dict[str, dict],
    template_targets: list[dict],
) -> list[McpPreviewAnchor]:
    """Build preview anchors from viewpoint targets and feature geometry."""
    anchors: list[McpPreviewAnchor] = []

    for target in vp.get("targets", []):
        feat_id = target.get("featureId", "")
        feat = feature_index.get(feat_id)
        if feat is None:
            continue

        # Get feature center coordinates
        if "center" in feat:
            lat = feat["center"]["lat"]
            lng = feat["center"]["lng"]
        elif "path" in feat:
            path = feat["path"]
            mid = path[len(path) // 2]
            lat = mid["lat"]
            lng = mid["lng"]
        else:
            continue

        alt = feat.get("elevationMeters", 0.0)

        anchors.append(McpPreviewAnchor(
            id=feat_id,
            label=target.get("role"),
            lat=lat,
            lng=lng,
            alt_meters=alt,
            desired_normalized_x=target.get("xNorm", 0.5),
            desired_normalized_y=target.get("yNorm", 0.5),
        ))

    return anchors


def convert_viewpoint(
    vp: dict,
    *,
    scene_dict: dict,
    feature_index: dict[str, dict],
    request_radius_meters: float,
    include_preview_input: bool = True,
) -> McpViewpoint:
    """Convert an internal viewpoint dict to an MCP viewpoint."""
    camera = _convert_camera(vp["camera"])
    mcp_composition = composition_to_mcp(vp["composition"])

    targets = [
        McpViewpointTarget(
            feature_id=t["featureId"],
            role=t["role"],
            x_norm=t["xNorm"],
            y_norm=t["yNorm"],
        )
        for t in vp.get("targets", [])
    ]

    score_breakdown = _convert_score_breakdown(vp.get("scoreBreakdown", {}))

    validation = McpValidation(
        clearance_meters=vp.get("validation", {}).get("clearanceMeters", 0.0),
        visible_target_ids=vp.get("validation", {}).get("visibleTargetIds", []),
    )

    preview_input = None
    if include_preview_input:
        anchors = _build_preview_anchors(vp, feature_index, [])

        scene_center = scene_dict.get("center", {})
        preview_input = McpPreviewInput(
            camera=camera,
            scene=McpPreviewScene(
                center={"lat": scene_center.get("lat", 0), "lng": scene_center.get("lng", 0)},
                radius_meters=request_radius_meters,
                scene_id=scene_dict.get("id"),
                scene_type=scene_dict.get("type"),
                scene_summary=scene_dict.get("summary"),
                feature_ids=scene_dict.get("featureIds"),
            ),
            composition=McpPreviewComposition(
                target_template=mcp_composition,
                subject_label=targets[0].role if targets else None,
                horizon_ratio=_get_horizon_ratio_for_composition(vp["composition"]),
                anchors=anchors if anchors else None,
            ),
        )

    return McpViewpoint(
        id=vp["id"],
        scene=vp.get("sceneId", ""),
        composition=mcp_composition,
        camera=camera,
        targets=targets,
        distance_meters_approx=vp.get("distanceMetersApprox", 0.0),
        score=vp.get("score", 0.0),
        score_breakdown=score_breakdown,
        validation=validation,
        preview_input=preview_input,
    )


def _get_horizon_ratio_for_composition(composition: str) -> float:
    """Get default horizon ratio for a composition type."""
    ratios = {
        "ruleOfThirds": 0.333,
        "goldenRatio": 0.382,
        "leadingLine": 0.45,
        "symmetry": 0.5,
    }
    return ratios.get(composition, 0.333)


def convert_summary(summary: dict) -> McpViewpointsSummary:
    """Convert camelCase viewpoint summary to MCP format."""
    rejected = summary.get("candidatesRejected", {})
    return McpViewpointsSummary(
        scene_count=summary.get("sceneCount", 0),
        eligible_scene_count=summary.get("eligibleSceneCount", 0),
        candidates_generated=summary.get("candidatesGenerated", 0),
        candidates_rejected=rejected,
        returned=summary.get("returned", 0),
    )


def convert_request_echo(
    lat: float,
    lng: float,
    radius_meters: float,
    zoom_used: int,
    weights: dict,
    compositions_mcp: list[McpCompositionType],
    max_viewpoints: int,
    max_per_scene: int,
) -> McpViewpointsRequest:
    """Build an MCP request echo."""
    return McpViewpointsRequest(
        center={"lat": lat, "lng": lng},
        radius_meters=radius_meters,
        zoom_used=zoom_used,
        weights=weights,
        compositions=compositions_mcp,
        max_viewpoints=max_viewpoints,
        max_per_scene=max_per_scene,
    )
