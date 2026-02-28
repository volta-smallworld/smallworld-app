"""Preview render endpoint."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from smallworld_api.config import settings
from smallworld_api.models.previews import (
    CameraMetadata,
    CompositionMetadata,
    CompositionTarget,
    ImageArtifact,
    LocationMetadata,
    PreviewMetadata,
    PreviewRenderRequest,
    PreviewRenderResponse,
    PreviewWarning,
    SceneMetadata,
    TimingsMs,
)
from smallworld_api.services.composition_verifier import verify_composition
from smallworld_api.services.preview_artifacts import (
    artifact_url,
    cleanup_expired,
    ensure_preview_dir,
    generate_preview_id,
    get_artifact_path,
    save_artifact,
    save_manifest,
    save_request,
)
from smallworld_api.services.preview_enhancement import (
    DEFAULT_ENHANCEMENT_PROMPT,
    EnhancementError,
    EnhancementNotConfiguredError,
    enhance_preview,
)
from smallworld_api.services.preview_renderer import (
    RenderError,
    RenderTimeoutError,
    render_preview,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────


def _heading_to_compass(heading: float) -> str:
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    index = round(heading / 22.5) % 16
    return directions[index]


def _build_summary(req: PreviewRenderRequest, compass: str) -> str:
    scene_type = req.scene.sceneType or "terrain"
    template = req.composition.targetTemplate.value.replace("_", "-")
    return (
        f"{scene_type.capitalize()} preview facing {compass} at "
        f"{req.camera.headingDeg:.0f} degrees with {template} framing."
    )


# ── Routes ────────────────────────────────────────────────────────────────


@router.post("/render", response_model=PreviewRenderResponse)
async def render_preview_endpoint(req: PreviewRenderRequest):
    start_time = time.monotonic()
    warnings: list[PreviewWarning] = []

    # 1. Check render backend configuration
    if not settings.preview_renderer_base_url:
        raise HTTPException(status_code=503, detail="Render backend not configured")

    # 2. Best-effort cleanup of expired artifacts
    try:
        cleanup_expired(
            settings.preview_artifacts_dir, settings.preview_artifact_ttl_hours
        )
    except Exception:
        logger.warning("Artifact cleanup failed", exc_info=True)

    # 3. Allocate preview ID and directory
    preview_id = generate_preview_id()
    preview_dir = ensure_preview_dir(settings.preview_artifacts_dir, preview_id)

    # 4. Save request for debugging
    save_request(preview_dir, req.model_dump())

    # 5. Run renderer
    render_start = time.monotonic()
    try:
        render_result = await render_preview(
            base_url=settings.preview_renderer_base_url,
            camera_lat=req.camera.position.lat,
            camera_lng=req.camera.position.lng,
            camera_alt=req.camera.position.altMeters,
            heading_deg=req.camera.headingDeg,
            pitch_deg=req.camera.pitchDeg,
            roll_deg=req.camera.rollDeg,
            fov_deg=req.camera.fovDeg,
            viewport_width=req.viewport.width,
            viewport_height=req.viewport.height,
            output_path=preview_dir / "raw.png",
            timeout_seconds=settings.preview_render_timeout_seconds,
            cesium_ion_token=settings.cesium_ion_token,
            mapbox_access_token=settings.mapbox_access_token,
        )
    except RenderTimeoutError:
        raise HTTPException(status_code=504, detail="Render timed out")
    except RenderError as e:
        raise HTTPException(status_code=502, detail=f"Render failed: {e}")
    render_ms = int((time.monotonic() - render_start) * 1000)

    # Persist raw artifact
    raw_bytes = render_result.image_path.read_bytes()
    save_artifact(preview_dir, "raw", raw_bytes)

    # 6. Run composition verification
    verification = verify_composition(
        camera_lat=req.camera.position.lat,
        camera_lng=req.camera.position.lng,
        camera_alt_meters=req.camera.position.altMeters,
        heading_deg=req.camera.headingDeg,
        pitch_deg=req.camera.pitchDeg,
        roll_deg=req.camera.rollDeg,
        fov_deg=req.camera.fovDeg,
        viewport_width=req.viewport.width,
        viewport_height=req.viewport.height,
        template=req.composition.targetTemplate,
        anchors=req.composition.anchors,
        horizon_ratio=req.composition.horizonRatio,
    )

    # 7. Run enhancement if requested
    enhanced_image: ImageArtifact | None = None
    enhancement_ms: int | None = None
    status = "completed"

    if req.enhancement.enabled:
        enhancement_start = time.monotonic()
        prompt = req.enhancement.prompt or DEFAULT_ENHANCEMENT_PROMPT
        try:
            enhancement_result = await enhance_preview(
                raw_image_path=render_result.image_path,
                output_path=preview_dir / "enhanced.png",
                prompt=prompt,
                api_key=settings.gemini_api_key,
                model=settings.gemini_image_model,
            )
            enhanced_bytes = enhancement_result.image_path.read_bytes()
            save_artifact(preview_dir, "enhanced", enhanced_bytes)
            enhanced_image = ImageArtifact(
                url=artifact_url(preview_id, "enhanced"),
                width=req.viewport.width,
                height=req.viewport.height,
            )
            enhancement_ms = int((time.monotonic() - enhancement_start) * 1000)
        except EnhancementNotConfiguredError:
            status = "completed_with_warnings"
            warnings.append(
                PreviewWarning(
                    code="enhancement_not_configured",
                    message="Enhancement is not configured. Set GEMINI_API_KEY and GEMINI_IMAGE_MODEL.",
                )
            )
        except EnhancementError as e:
            status = "completed_with_warnings"
            warnings.append(
                PreviewWarning(
                    code="enhancement_failed",
                    message=f"Enhancement failed: {e}",
                )
            )
            enhancement_ms = int((time.monotonic() - enhancement_start) * 1000)

    # 8. Build metadata
    compass = _heading_to_compass(req.camera.headingDeg)

    metadata = PreviewMetadata(
        camera=CameraMetadata(
            lat=req.camera.position.lat,
            lng=req.camera.position.lng,
            altMeters=req.camera.position.altMeters,
            headingDeg=req.camera.headingDeg,
            pitchDeg=req.camera.pitchDeg,
            rollDeg=req.camera.rollDeg,
            fovDeg=req.camera.fovDeg,
            compassDirection=compass,
        ),
        location=LocationMetadata(
            sceneCenter={
                "lat": req.scene.center.lat,
                "lng": req.scene.center.lng,
            },
            radiusMeters=req.scene.radiusMeters,
            googleMapsUrl=(
                f"https://www.google.com/maps/search/?api=1"
                f"&query={req.scene.center.lat},{req.scene.center.lng}"
            ),
            geoUri=f"geo:{req.scene.center.lat},{req.scene.center.lng}",
        ),
        scene=SceneMetadata(
            sceneId=req.scene.sceneId,
            sceneType=req.scene.sceneType,
            sceneSummary=req.scene.sceneSummary,
            featureIds=req.scene.featureIds,
        ),
        composition=CompositionMetadata(
            target=CompositionTarget(
                template=req.composition.targetTemplate.value,
                subjectLabel=req.composition.subjectLabel,
                horizonRatio=req.composition.horizonRatio,
            ),
            verified=verification,
        ),
        summary=_build_summary(req, compass),
    )

    total_ms = int((time.monotonic() - start_time) * 1000)

    # 9. Build and save response
    response = PreviewRenderResponse(
        id=preview_id,
        status=status,
        warnings=warnings,
        rawImage=ImageArtifact(
            url=artifact_url(preview_id, "raw"),
            width=req.viewport.width,
            height=req.viewport.height,
        ),
        enhancedImage=enhanced_image,
        metadata=metadata,
        timingsMs=TimingsMs(
            render=render_ms,
            enhancement=enhancement_ms,
            total=total_ms,
        ),
    )

    save_manifest(preview_dir, response.model_dump())

    return response


@router.get("/{preview_id}/artifacts/{variant}")
async def get_artifact(preview_id: str, variant: str):
    if variant not in ("raw", "enhanced"):
        raise HTTPException(status_code=404, detail="Unknown artifact variant")

    path = get_artifact_path(settings.preview_artifacts_dir, preview_id, variant)
    if path is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(path, media_type="image/png")
