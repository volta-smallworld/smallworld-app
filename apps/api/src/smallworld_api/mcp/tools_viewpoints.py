"""MCP tool: terrain_find_viewpoints."""

from __future__ import annotations

import httpx

from smallworld_api.mcp.adapters import (
    convert_request_echo,
    convert_summary,
    convert_viewpoint,
)
from smallworld_api.mcp.schemas import (
    McpCompositionType,
    TerrainFindViewpointsInput,
    composition_from_mcp,
)
from smallworld_api.mcp.server import mcp
from smallworld_api.services.analysis import (
    build_interest_raster,
    build_layer_contributions,
    extract_hotspots,
)
from smallworld_api.services.derivatives import (
    compute_local_relief,
    compute_profile_curvature,
    compute_slope_degrees,
)
from smallworld_api.services.features import (
    extract_cliffs,
    extract_peaks,
    extract_ridges,
    extract_water_channels,
)
from smallworld_api.services.scenes import group_scenes
from smallworld_api.services.terrarium import fetch_dem_snapshot
from smallworld_api.services.viewpoints import generate_viewpoints


@mcp.tool()
async def terrain_find_viewpoints(
    lat: float,
    lng: float,
    radius_meters: float,
    weights: dict | None = None,
    compositions: list[str] | None = None,
    max_viewpoints: int = 12,
    max_per_scene: int = 3,
    include_preview_input: bool = True,
) -> dict:
    """Generate ranked camera viewpoints for terrain around a geographic point.

    Returns viewpoints sorted by beauty score, each with camera pose,
    composition targets, and an optional preview_input that can be passed
    directly to preview_render_pose.

    Args:
        lat: Center latitude (-90 to 90)
        lng: Center longitude (-180 to 180)
        radius_meters: Search radius in meters (1000 to 50000)
        weights: Analysis weights dict with keys peaks, ridges, cliffs, water, relief (0-2 each)
        compositions: Composition types to generate (rule_of_thirds, golden_ratio, leading_line, symmetry)
        max_viewpoints: Maximum viewpoints to return (1-25, default 12)
        max_per_scene: Maximum viewpoints per scene (1-5, default 3)
        include_preview_input: Include preview_input for each viewpoint (default true)
    """
    # Parse composition types
    mcp_compositions: list[McpCompositionType] | None = None
    if compositions:
        mcp_compositions = [McpCompositionType(c) for c in compositions]

    # Validate via Pydantic
    inp = TerrainFindViewpointsInput(
        lat=lat, lng=lng, radius_meters=radius_meters,
        weights=weights, compositions=mcp_compositions,
        max_viewpoints=max_viewpoints, max_per_scene=max_per_scene,
        include_preview_input=include_preview_input,
    )

    # Resolve defaults
    weights_dict = inp.weights or {
        "peaks": 1.0, "ridges": 0.9, "cliffs": 0.8, "water": 0.7, "relief": 1.0,
    }

    all_mcp_compositions = inp.compositions or list(McpCompositionType)
    rest_compositions = [composition_from_mcp(c.value) for c in all_mcp_compositions]

    # Fetch terrain
    try:
        snap = await fetch_dem_snapshot(
            lat=inp.lat, lng=inp.lng, radius_m=inp.radius_meters,
        )
    except ValueError as e:
        raise ValueError(f"Invalid terrain request: {e}")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Upstream tile fetch failed (HTTP {e.response.status_code}). Try again.")
    except httpx.RequestError as e:
        raise RuntimeError(f"Upstream tile fetch failed: {e}. Try again.")

    dem = snap.dem
    cell_size = snap.cell_size_meters
    bounds = snap.bounds

    # Recompute terrain analysis
    slope = compute_slope_degrees(dem, cell_size)
    curvature = compute_profile_curvature(dem, cell_size)
    relief = compute_local_relief(dem)

    peaks = extract_peaks(dem, bounds)
    ridges = extract_ridges(dem, bounds, cell_size)
    cliffs = extract_cliffs(slope, curvature, bounds, dem)
    water_channels = extract_water_channels(dem, bounds, cell_size)

    interest = build_interest_raster(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds, weights_dict,
    )

    layer_contribs = build_layer_contributions(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds,
    )
    hotspots = extract_hotspots(interest, bounds, weights_dict, layer_contribs)

    all_features = {
        "peaks": peaks, "ridges": ridges,
        "cliffs": cliffs, "waterChannels": water_channels,
    }
    scenes = group_scenes(hotspots, all_features)

    # Generate viewpoints using existing pipeline
    result = generate_viewpoints(
        dem=dem,
        bounds=bounds,
        cell_size_meters=cell_size,
        scenes=scenes,
        all_features=all_features,
        interest_raster=interest,
        compositions=rest_compositions,
        max_viewpoints=inp.max_viewpoints,
        max_per_scene=inp.max_per_scene,
    )

    # Build feature index for adapter
    feature_index: dict[str, dict] = {}
    for feat_list in all_features.values():
        for feat in feat_list:
            fid = feat.get("id")
            if fid:
                feature_index[fid] = feat

    # Build scene index
    scene_index: dict[str, dict] = {}
    for sc in scenes:
        sid = sc.get("id")
        if sid:
            scene_index[sid] = sc

    # Convert viewpoints to MCP format
    mcp_viewpoints = []
    for vp in result["viewpoints"]:
        scene_id = vp.get("sceneId", "")
        scene_dict = scene_index.get(scene_id, {})
        mcp_vp = convert_viewpoint(
            vp,
            scene_dict=scene_dict,
            feature_index=feature_index,
            request_radius_meters=inp.radius_meters,
            include_preview_input=inp.include_preview_input,
        )
        mcp_viewpoints.append(mcp_vp)

    # Build response
    request_echo = convert_request_echo(
        lat=inp.lat,
        lng=inp.lng,
        radius_meters=inp.radius_meters,
        zoom_used=snap.zoom,
        weights=weights_dict,
        compositions_mcp=all_mcp_compositions,
        max_viewpoints=inp.max_viewpoints,
        max_per_scene=inp.max_per_scene,
    )

    summary = convert_summary(result["summary"])

    return {
        "request": request_echo.model_dump(),
        "summary": summary.model_dump(),
        "viewpoints": [vp.model_dump() for vp in mcp_viewpoints],
        "source": "aws-terrarium",
    }
