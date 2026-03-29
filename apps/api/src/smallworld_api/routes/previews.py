"""Preview render endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from smallworld_api.config import settings
from smallworld_api.models.previews import (
    CameraMetadata,
    CompositionMetadata,
    CompositionTarget,
    ImageArtifact,
    LocationMetadata,
    PreviewCapabilitiesResponse,
    PreviewMetadata,
    PreviewRenderRequest,
    PreviewRenderResponse,
    PreviewWarning,
    SceneMetadata,
    TimingsMs,
)
from smallworld_api.services.preview_artifacts import get_artifact_path
from smallworld_api.services.preview_renderer import RenderError, RenderTimeoutError
from smallworld_api.services.previews import (
    PreviewRendererNotConfiguredError,
    render_preview_pipeline,
)

router = APIRouter()
logger = logging.getLogger(__name__)

PROVIDER_ORDER = ["google_3d", "ion", "osm"]


@router.get("/capabilities", response_model=PreviewCapabilitiesResponse)
async def get_capabilities():
    available: list[str] = []
    if settings.google_maps_api_key:
        available.append("google_3d")
    if settings.cesium_ion_token:
        available.append("ion")
    available.append("osm")

    renderer_configured = bool(settings.preview_renderer_base_url)
    enabled = renderer_configured
    active_provider = available[0] if available else "osm"

    message = None
    if not renderer_configured:
        message = "Preview renderer is not configured (PREVIEW_RENDERER_BASE_URL is empty)."

    return PreviewCapabilitiesResponse(
        enabled=enabled,
        availableProviders=available,
        providerOrder=PROVIDER_ORDER,
        activeProvider=active_provider,
        eagerCount=settings.preview_eager_count,
        message=message,
        rendererConfigured=renderer_configured,
    )


@router.post("/render", response_model=PreviewRenderResponse)
async def render_preview_endpoint(req: PreviewRenderRequest):
    # Convert anchors to dicts for the shared service
    anchors_dicts = None
    if req.composition.anchors:
        anchors_dicts = [
            {
                "id": a.id,
                "label": a.label,
                "lat": a.lat,
                "lng": a.lng,
                "altMeters": a.altMeters,
                "desiredNormalizedX": a.desiredNormalizedX,
                "desiredNormalizedY": a.desiredNormalizedY,
            }
            for a in req.composition.anchors
        ]

    try:
        result = await render_preview_pipeline(
            camera_lat=req.camera.position.lat,
            camera_lng=req.camera.position.lng,
            camera_alt_meters=req.camera.position.altMeters,
            heading_deg=req.camera.headingDeg,
            pitch_deg=req.camera.pitchDeg,
            roll_deg=req.camera.rollDeg,
            fov_deg=req.camera.fovDeg,
            viewport_width=req.viewport.width,
            viewport_height=req.viewport.height,
            scene_center_lat=req.scene.center.lat,
            scene_center_lng=req.scene.center.lng,
            scene_radius_meters=req.scene.radiusMeters,
            scene_id=req.scene.sceneId,
            scene_type=req.scene.sceneType,
            scene_summary=req.scene.sceneSummary,
            feature_ids=req.scene.featureIds,
            target_template=req.composition.targetTemplate.value,
            subject_label=req.composition.subjectLabel,
            horizon_ratio=req.composition.horizonRatio,
            anchors=anchors_dicts,
            enhancement_enabled=req.enhancement.enabled,
            enhancement_prompt=req.enhancement.prompt,
        )
    except PreviewRendererNotConfiguredError:
        raise HTTPException(status_code=503, detail="Render backend not configured")
    except RenderTimeoutError:
        raise HTTPException(status_code=504, detail="Render timed out")
    except RenderError as e:
        raise HTTPException(status_code=502, detail=f"Render failed: {e}")

    # Map pipeline result to REST response (camelCase)
    cam = result.camera_metadata
    loc = result.location_metadata
    scene_meta = result.scene_metadata
    comp_meta = result.composition_metadata

    metadata = PreviewMetadata(
        camera=CameraMetadata(
            lat=cam["lat"],
            lng=cam["lng"],
            altMeters=cam["alt_meters"],
            headingDeg=cam["heading_deg"],
            pitchDeg=cam["pitch_deg"],
            rollDeg=cam["roll_deg"],
            fovDeg=cam["fov_deg"],
            compassDirection=cam["compass_direction"],
        ),
        location=LocationMetadata(
            sceneCenter={
                "lat": loc["scene_center"]["lat"],
                "lng": loc["scene_center"]["lng"],
            },
            radiusMeters=loc["radius_meters"],
            googleMapsUrl=loc["google_maps_url"],
            geoUri=loc["geo_uri"],
        ),
        scene=SceneMetadata(
            sceneId=scene_meta["scene_id"],
            sceneType=scene_meta["scene_type"],
            sceneSummary=scene_meta["scene_summary"],
            featureIds=scene_meta["feature_ids"],
        ),
        composition=CompositionMetadata(
            target=CompositionTarget(
                template=comp_meta["target"]["template"],
                subjectLabel=comp_meta["target"]["subject_label"],
                horizonRatio=comp_meta["target"]["horizon_ratio"],
            ),
            verified=result.verification,
        ),
        summary=result.summary,
    )

    raw_image = None
    if result.raw_artifact:
        raw_image = ImageArtifact(
            url=result.raw_artifact.relative_url,
            width=result.raw_artifact.width,
            height=result.raw_artifact.height,
        )

    enhanced_image = None
    if result.enhanced_artifact:
        enhanced_image = ImageArtifact(
            url=result.enhanced_artifact.relative_url,
            width=result.enhanced_artifact.width,
            height=result.enhanced_artifact.height,
        )

    return PreviewRenderResponse(
        id=result.preview_id,
        status=result.status,
        warnings=[
            PreviewWarning(code=w.code, message=w.message)
            for w in result.warnings
        ],
        rawImage=raw_image,
        enhancedImage=enhanced_image,
        metadata=metadata,
        timingsMs=TimingsMs(
            render=result.timings_ms.get("render"),
            enhancement=result.timings_ms.get("enhancement"),
            total=result.timings_ms["total"],
        ),
    )


@router.get("/{preview_id}/artifacts/{variant}")
async def get_artifact(preview_id: str, variant: str):
    if variant not in ("raw", "enhanced"):
        raise HTTPException(status_code=404, detail="Unknown artifact variant")

    path = get_artifact_path(settings.preview_artifacts_dir, preview_id, variant)
    if path is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(path, media_type="image/png")
