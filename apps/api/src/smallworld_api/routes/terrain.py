import httpx
import numpy as np
from fastapi import APIRouter, HTTPException

from smallworld_api.models.terrain import (
    AnalysisWeights,
    ElevationGridRequest,
    ElevationGridResponse,
    TerrainAnalysisRequest,
    TerrainAnalysisResponse,
)
from smallworld_api.services.analysis import (
    DEFAULT_ANALYSIS_WEIGHTS,
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
from smallworld_api.services.terrarium import fetch_dem_snapshot, get_elevation_grid

router = APIRouter()


@router.post("/elevation-grid", response_model=ElevationGridResponse)
async def elevation_grid(req: ElevationGridRequest):
    try:
        result = await get_elevation_grid(
            lat=req.center.lat,
            lng=req.center.lng,
            radius_m=req.radiusMeters,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream tile fetch failed: {e.response.status_code}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream tile fetch failed: {e}",
        )
    return result


@router.post("/analyze", response_model=TerrainAnalysisResponse)
async def analyze_terrain(req: TerrainAnalysisRequest):
    weights = req.weights or AnalysisWeights()
    weights_dict = {
        "peaks": weights.peaks,
        "ridges": weights.ridges,
        "cliffs": weights.cliffs,
        "water": weights.water,
        "relief": weights.relief,
    }

    try:
        snap = await fetch_dem_snapshot(
            lat=req.center.lat,
            lng=req.center.lng,
            radius_m=req.radiusMeters,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream tile fetch failed: {e.response.status_code}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream tile fetch failed: {e}",
        )

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

    # Interest surface
    interest = build_interest_raster(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds, weights_dict
    )

    # Hotspots
    layer_contribs = build_layer_contributions(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds
    )
    hotspots = extract_hotspots(interest, bounds, weights_dict, layer_contribs)

    # Scenes
    all_features = {
        "peaks": peaks,
        "ridges": ridges,
        "cliffs": cliffs,
        "waterChannels": water_channels,
    }
    scenes = group_scenes(hotspots, all_features)

    def _metric(arr: np.ndarray) -> dict:
        return {
            "min": round(float(np.min(arr)), 1),
            "max": round(float(np.max(arr)), 1),
            "mean": round(float(np.mean(arr)), 1),
        }

    return {
        "request": {
            "center": {"lat": req.center.lat, "lng": req.center.lng},
            "radiusMeters": req.radiusMeters,
            "zoomUsed": snap.zoom,
            "weights": weights_dict,
        },
        "bounds": {
            "north": round(bounds.north, 6),
            "south": round(bounds.south, 6),
            "east": round(bounds.east, 6),
            "west": round(bounds.west, 6),
        },
        "grid": {
            "width": dem.shape[1],
            "height": dem.shape[0],
            "cellSizeMetersApprox": cell_size,
        },
        "summary": {
            "elevationMeters": _metric(dem),
            "slopeDegrees": _metric(slope),
            "localReliefMeters": _metric(relief),
            "interestScore": _metric(interest),
        },
        "features": {
            "peaks": peaks,
            "ridges": ridges,
            "cliffs": cliffs,
            "waterChannels": water_channels,
        },
        "hotspots": hotspots,
        "scenes": scenes,
        "tiles": [{"z": z, "x": x, "y": y} for z, x, y in snap.tile_coords],
        "source": "aws-terrarium",
    }
