"""MCP tool: terrain_analyze_area."""

from __future__ import annotations

import httpx
import numpy as np

from smallworld_api.mcp.schemas import TerrainAnalyzeAreaInput, TerrainAnalyzeAreaResult
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


@mcp.tool()
async def terrain_analyze_area(
    lat: float,
    lng: float,
    radius_meters: float,
    zoom: int | None = None,
    include_elevations: bool = False,
) -> dict:
    """Analyze terrain around a geographic point.

    Returns terrain features (peaks, ridges, cliffs, water channels),
    interest hotspots, scene seeds, and summary statistics.

    Args:
        lat: Center latitude (-90 to 90)
        lng: Center longitude (-180 to 180)
        radius_meters: Search radius in meters (1000 to 50000)
        zoom: Tile zoom level override (default: server config)
        include_elevations: Include the 128x128 elevation matrix (default: false)
    """
    # Validate input via Pydantic
    inp = TerrainAnalyzeAreaInput(
        lat=lat, lng=lng, radius_meters=radius_meters,
        zoom=zoom, include_elevations=include_elevations,
    )

    try:
        snap = await fetch_dem_snapshot(
            lat=inp.lat, lng=inp.lng, radius_m=inp.radius_meters, zoom=inp.zoom,
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

    # Derivatives
    slope = compute_slope_degrees(dem, cell_size)
    curvature = compute_profile_curvature(dem, cell_size)
    relief = compute_local_relief(dem)

    # Features
    peaks = extract_peaks(dem, bounds)
    ridges = extract_ridges(dem, bounds, cell_size)
    cliffs = extract_cliffs(slope, curvature, bounds, dem)
    water_channels = extract_water_channels(dem, bounds, cell_size)

    # Default weights
    weights_dict = {
        "peaks": 1.0, "ridges": 0.9, "cliffs": 0.8, "water": 0.7, "relief": 1.0,
    }

    # Interest surface
    interest = build_interest_raster(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds, weights_dict,
    )

    # Hotspots
    layer_contribs = build_layer_contributions(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds,
    )
    hotspots = extract_hotspots(interest, bounds, weights_dict, layer_contribs)

    # Scenes
    all_features = {
        "peaks": peaks, "ridges": ridges,
        "cliffs": cliffs, "waterChannels": water_channels,
    }
    scenes = group_scenes(hotspots, all_features)

    def _metric(arr: np.ndarray) -> dict:
        return {
            "min": round(float(np.min(arr)), 1),
            "max": round(float(np.max(arr)), 1),
            "mean": round(float(np.mean(arr)), 1),
        }

    elevations = None
    if inp.include_elevations:
        elevations = [[round(float(v), 1) for v in row] for row in dem.tolist()]

    result = TerrainAnalyzeAreaResult(
        center={"lat": inp.lat, "lng": inp.lng},
        radius_meters=inp.radius_meters,
        zoom_used=snap.zoom,
        bounds={
            "north": round(bounds.north, 6),
            "south": round(bounds.south, 6),
            "east": round(bounds.east, 6),
            "west": round(bounds.west, 6),
        },
        grid={
            "width": dem.shape[1],
            "height": dem.shape[0],
            "cell_size_meters_approx": cell_size,
        },
        summary={
            "elevation_meters": _metric(dem),
            "slope_degrees": _metric(slope),
            "local_relief_meters": _metric(relief),
            "interest_score": _metric(interest),
        },
        features={
            "peaks": peaks,
            "ridges": ridges,
            "cliffs": cliffs,
            "water_channels": water_channels,
        },
        hotspots=hotspots,
        scenes=scenes,
        tiles=[{"z": z, "x": x, "y": y} for z, x, y in snap.tile_coords],
        elevations=elevations,
    )

    return result.model_dump()
