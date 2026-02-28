"""Style reference routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import httpx
import numpy as np

from smallworld_api.config import settings
from smallworld_api.models.terrain import AnalysisWeights
from smallworld_api.models.style import (
    StyleReferenceCapability,
    StyleReferenceUploadResponse,
    StyleVerificationResult,
    StyleViewpointSearchRequest,
    StyleViewpointSearchResponse,
)
from smallworld_api.services.style_references import (
    check_style_capabilities,
    cleanup_expired_references,
    load_reference_artifacts,
    save_reference_artifacts,
)
from smallworld_api.services.style_fingerprint import (
    extract_fingerprint,
    normalize_image,
)
from smallworld_api.services.style_matching import (
    find_style_viewpoints,
)
from smallworld_api.services.style_verification import (
    verify_rendered_preview,
)
from smallworld_api.services.terrarium import fetch_dem_snapshot
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
from smallworld_api.services.analysis import (
    build_interest_raster,
    build_layer_contributions,
    extract_hotspots,
)
from smallworld_api.services.scenes import group_scenes

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.get("/style-references/capabilities", response_model=StyleReferenceCapability)
async def style_capabilities():
    return check_style_capabilities()


@router.post("/style-references", response_model=StyleReferenceUploadResponse)
async def upload_style_reference(
    file: UploadFile = File(...),
    label: str | None = Form(default=None),
):
    cap = check_style_capabilities()
    if not cap.enabled:
        raise HTTPException(status_code=503, detail=cap.message or "Style models unavailable")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported content type: {file.content_type}. Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    data = await file.read()
    if len(data) > settings.style_upload_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(data)} bytes (max {settings.style_upload_max_bytes})",
        )

    cleanup_expired_references()

    normalized, width, height = normalize_image(data)
    fingerprint_result = extract_fingerprint(normalized)

    reference_id = save_reference_artifacts(
        image_data=data,
        normalized=normalized,
        fingerprint_result=fingerprint_result,
        filename=file.filename or "upload",
        content_type=file.content_type or "image/jpeg",
        label=label,
    )

    return StyleReferenceUploadResponse(
        referenceId=reference_id,
        label=label,
        filename=file.filename or "upload",
        contentType=file.content_type or "image/jpeg",
        width=width,
        height=height,
        fingerprintSummary=fingerprint_result["summary"],
        artifacts={"edgeMapAvailable": True},
    )


@router.post("/terrain/style-viewpoints", response_model=StyleViewpointSearchResponse)
async def style_viewpoints(req: StyleViewpointSearchRequest):
    cap = check_style_capabilities()
    if not cap.enabled:
        raise HTTPException(status_code=503, detail=cap.message or "Style models unavailable")

    artifacts = load_reference_artifacts(req.referenceId)
    if artifacts is None:
        raise HTTPException(status_code=404, detail=f"Reference {req.referenceId} not found or expired")

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
        raise HTTPException(status_code=502, detail=f"Upstream tile fetch failed: {e}")

    dem = snap.dem
    cell_size = snap.cell_size_meters
    bounds = snap.bounds

    slope = compute_slope_degrees(dem, cell_size)
    curvature = compute_profile_curvature(dem, cell_size)
    relief = compute_local_relief(dem)

    peaks = extract_peaks(dem, bounds)
    ridges = extract_ridges(dem, bounds, cell_size)
    cliffs = extract_cliffs(slope, curvature, bounds, dem)
    water_channels = extract_water_channels(dem, bounds, cell_size)

    interest = build_interest_raster(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds, weights_dict
    )

    layer_contribs = build_layer_contributions(
        dem, relief, curvature, peaks, ridges, cliffs, water_channels, bounds
    )
    hotspots = extract_hotspots(interest, bounds, weights_dict, layer_contribs)

    all_features = {
        "peaks": peaks,
        "ridges": ridges,
        "cliffs": cliffs,
        "waterChannels": water_channels,
    }
    scenes = group_scenes(hotspots, all_features)

    compositions_str = [c.value for c in req.compositions]

    result = find_style_viewpoints(
        dem=dem,
        bounds=bounds,
        cell_size_meters=cell_size,
        scenes=scenes,
        all_features=all_features,
        interest_raster=interest,
        compositions=compositions_str,
        reference_fingerprint=artifacts["fingerprint"],
        reference_metadata=artifacts["metadata"],
        max_viewpoints=req.maxViewpoints,
        max_per_scene=req.maxPerScene,
        top_patch_count=req.topPatchCount,
    )

    return StyleViewpointSearchResponse(
        request={
            "center": {"lat": req.center.lat, "lng": req.center.lng},
            "radiusMeters": req.radiusMeters,
            "zoomUsed": snap.zoom,
            "weights": weights_dict,
            "compositions": compositions_str,
            "maxViewpoints": req.maxViewpoints,
            "maxPerScene": req.maxPerScene,
            "referenceId": req.referenceId,
            "topPatchCount": req.topPatchCount,
        },
        reference={
            "referenceId": req.referenceId,
            "label": artifacts["metadata"].get("label"),
        },
        summary=result["summary"],
        viewpoints=result["viewpoints"],
        source="aws-terrarium",
    )


@router.post(
    "/style-references/{reference_id}/verify-render",
    response_model=StyleVerificationResult,
)
async def verify_render(
    reference_id: str,
    viewpointId: str = Form(...),
    preview: UploadFile = File(...),
    composition: str = Form(...),
    preRenderScore: float = Form(...),
):
    cap = check_style_capabilities()
    if not cap.enabled:
        raise HTTPException(status_code=503, detail=cap.message or "Style models unavailable")

    artifacts = load_reference_artifacts(reference_id)
    if artifacts is None:
        raise HTTPException(status_code=404, detail=f"Reference {reference_id} not found or expired")

    preview_data = await preview.read()
    if not preview_data:
        raise HTTPException(status_code=422, detail="Empty preview file")

    cleanup_expired_references()

    result = verify_rendered_preview(
        reference_artifacts=artifacts,
        preview_data=preview_data,
        pre_render_score=preRenderScore,
    )

    return StyleVerificationResult(
        referenceId=reference_id,
        viewpointId=viewpointId,
        **result,
    )
