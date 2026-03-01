"""Shared preview orchestration service.

Both the FastAPI preview route and the MCP preview tool call this
single pipeline so that rendering, enhancement, artifact storage,
and verification behavior stays consistent.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from smallworld_api.config import settings
from smallworld_api.services.composition_verifier import verify_composition
from smallworld_api.services.preview_artifacts import (
    artifact_url,
    cleanup_expired,
    ensure_preview_dir,
    generate_preview_id,
    save_artifact,
    save_manifest,
    save_request,
)
from smallworld_api.services.preview_enhancement import (
    EnhancementError,
    EnhancementNotConfiguredError,
    build_enhancement_prompt,
    enhance_preview as _enhance_preview,
)
from smallworld_api.services.preview_renderer import (
    RenderError,
    RenderTimeoutError,
    render_preview as _render_preview,
)

logger = logging.getLogger(__name__)


# ── Result types ─────────────────────────────────────────────────────────


@dataclass
class PreviewWarningItem:
    code: str
    message: str


@dataclass
class ArtifactInfo:
    local_path: str
    relative_url: str  # e.g. /api/v1/previews/{id}/artifacts/raw
    width: int
    height: int


@dataclass
class PreviewPipelineResult:
    preview_id: str
    status: str  # "completed" or "completed_with_warnings"
    warnings: list[PreviewWarningItem] = field(default_factory=list)
    raw_artifact: ArtifactInfo | None = None
    enhanced_artifact: ArtifactInfo | None = None
    camera_metadata: dict = field(default_factory=dict)
    location_metadata: dict = field(default_factory=dict)
    scene_metadata: dict = field(default_factory=dict)
    composition_metadata: dict = field(default_factory=dict)
    summary: str = ""
    timings_ms: dict = field(default_factory=dict)
    manifest_path: str = ""
    verification: dict | None = None


class PreviewRendererNotConfiguredError(Exception):
    """Raised when the render backend is not configured."""


# ── Helpers ──────────────────────────────────────────────────────────────


def _heading_to_compass(heading: float) -> str:
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    index = round(heading / 22.5) % 16
    return directions[index]


def _build_failure_manifest(
    *,
    preview_id: str,
    error: Exception,
    warnings: list[PreviewWarningItem],
    total_ms: int,
    render_attempts: list[dict],
) -> dict:
    return {
        "id": preview_id,
        "status": "failed",
        "warnings": [{"code": w.code, "message": w.message} for w in warnings],
        "error": {
            "type": error.__class__.__name__,
            "message": str(error),
        },
        "timings_ms": {
            "render": None,
            "enhancement": None,
            "total": total_ms,
        },
        "render_attempts": render_attempts,
    }


# ── Pipeline ─────────────────────────────────────────────────────────────


async def render_preview_pipeline(
    *,
    # Camera
    camera_lat: float,
    camera_lng: float,
    camera_alt_meters: float,
    heading_deg: float,
    pitch_deg: float,
    roll_deg: float,
    fov_deg: float,
    # Viewport
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    # Scene context
    scene_center_lat: float,
    scene_center_lng: float,
    scene_radius_meters: float,
    scene_id: str | None = None,
    scene_type: str | None = None,
    scene_summary: str | None = None,
    feature_ids: list[str] | None = None,
    # Composition
    target_template: str,
    subject_label: str | None = None,
    horizon_ratio: float | None = None,
    anchors: list[dict] | None = None,
    # Enhancement
    enhancement_enabled: bool = True,
    enhancement_prompt: str | None = None,
) -> PreviewPipelineResult:
    """Run the full preview render pipeline.

    Raises
    ------
    PreviewRendererNotConfiguredError
        When the render backend URL is not configured.
    RenderTimeoutError
        When rendering times out.
    RenderError
        When the render subprocess fails.
    """
    start_time = time.monotonic()
    warnings: list[PreviewWarningItem] = []

    width = viewport_width or settings.preview_default_width
    height = viewport_height or settings.preview_default_height

    # 1. Check render backend configuration
    if not settings.preview_renderer_base_url:
        raise PreviewRendererNotConfiguredError("Render backend not configured")

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
    save_request(preview_dir, {
        "camera": {
            "lat": camera_lat, "lng": camera_lng,
            "alt_meters": camera_alt_meters,
            "heading_deg": heading_deg, "pitch_deg": pitch_deg,
            "roll_deg": roll_deg, "fov_deg": fov_deg,
        },
        "viewport": {"width": width, "height": height},
        "scene": {
            "center": {"lat": scene_center_lat, "lng": scene_center_lng},
            "radius_meters": scene_radius_meters,
            "scene_id": scene_id, "scene_type": scene_type,
        },
        "composition": {"target_template": target_template},
        "enhancement": {"enabled": enhancement_enabled},
    })

    # 5. Run renderer, retrying without Google 3D if the first attempt fails.
    render_attempts: list[dict] = []
    render_ms: int | None = None
    render_result = None
    render_configs = [
        {
            "label": "default",
            "google_maps_api_key": settings.google_maps_api_key,
        }
    ]
    if settings.google_maps_api_key:
        render_configs.append(
            {
                "label": "retry_without_google_3d",
                "google_maps_api_key": "",
            }
        )

    last_render_error: RenderTimeoutError | RenderError | None = None
    for attempt_index, render_cfg in enumerate(render_configs):
        render_start = time.monotonic()
        try:
            render_result = await _render_preview(
                base_url=settings.preview_renderer_base_url,
                camera_lat=camera_lat,
                camera_lng=camera_lng,
                camera_alt=camera_alt_meters,
                heading_deg=heading_deg,
                pitch_deg=pitch_deg,
                roll_deg=roll_deg,
                fov_deg=fov_deg,
                viewport_width=width,
                viewport_height=height,
                output_path=preview_dir / "raw.png",
                timeout_seconds=settings.preview_render_timeout_seconds,
                cesium_ion_token=settings.cesium_ion_token,
                mapbox_access_token=settings.mapbox_access_token,
                google_maps_api_key=render_cfg["google_maps_api_key"],
            )
            render_ms = int((time.monotonic() - render_start) * 1000)
            render_attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "mode": render_cfg["label"],
                    "used_google_3d": bool(render_cfg["google_maps_api_key"]),
                    "status": "succeeded",
                    "duration_ms": render_ms,
                }
            )
            if attempt_index > 0:
                warnings.append(
                    PreviewWarningItem(
                        code="render_fallback_without_google_3d",
                        message="Google 3D rendering failed, so the preview was retried without Google 3D tiles.",
                    )
                )
            break
        except (RenderTimeoutError, RenderError) as exc:
            duration_ms = int((time.monotonic() - render_start) * 1000)
            render_attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "mode": render_cfg["label"],
                    "used_google_3d": bool(render_cfg["google_maps_api_key"]),
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error": str(exc),
                }
            )
            last_render_error = exc
            logger.warning(
                "Preview render attempt %s failed for %s: %s",
                attempt_index + 1,
                preview_id,
                exc,
            )
            continue

    if render_result is None:
        assert last_render_error is not None
        total_ms = int((time.monotonic() - start_time) * 1000)
        save_manifest(
            preview_dir,
            _build_failure_manifest(
                preview_id=preview_id,
                error=last_render_error,
                warnings=warnings,
                total_ms=total_ms,
                render_attempts=render_attempts,
            ),
        )
        raise last_render_error

    # Persist raw artifact
    raw_bytes = render_result.image_path.read_bytes()
    save_artifact(preview_dir, "raw", raw_bytes)

    raw_artifact = ArtifactInfo(
        local_path=str(preview_dir / "raw.png"),
        relative_url=artifact_url(preview_id, "raw"),
        width=width,
        height=height,
    )

    # 6. Run composition verification
    from smallworld_api.models.previews import (
        CompositionAnchor,
        CompositionTemplate as RestCompositionTemplate,
    )

    # Convert anchor dicts to CompositionAnchor models for the verifier
    anchor_models = None
    if anchors:
        anchor_models = []
        for a in anchors:
            anchor_models.append(CompositionAnchor(
                id=a.get("id", ""),
                label=a.get("label"),
                lat=a.get("lat", 0),
                lng=a.get("lng", 0),
                altMeters=a.get("altMeters", a.get("alt_meters", 0)),
                desiredNormalizedX=a.get(
                    "desiredNormalizedX",
                    a.get("desired_normalized_x", 0.5),
                ),
                desiredNormalizedY=a.get(
                    "desiredNormalizedY",
                    a.get("desired_normalized_y", 0.5),
                ),
            ))

    # Map template string to CompositionTemplate enum
    # Supports both snake_case (from REST) and camelCase (from MCP conversion)
    template_map = {
        "rule_of_thirds": RestCompositionTemplate.RULE_OF_THIRDS,
        "ruleOfThirds": RestCompositionTemplate.RULE_OF_THIRDS,
        "golden_ratio": RestCompositionTemplate.GOLDEN_RATIO,
        "goldenRatio": RestCompositionTemplate.GOLDEN_RATIO,
        "leading_line": RestCompositionTemplate.LEADING_LINE,
        "leadingLine": RestCompositionTemplate.LEADING_LINE,
        "symmetry": RestCompositionTemplate.SYMMETRY,
        "custom": RestCompositionTemplate.CUSTOM,
    }
    template_enum = template_map.get(target_template, RestCompositionTemplate.CUSTOM)

    verification = verify_composition(
        camera_lat=camera_lat,
        camera_lng=camera_lng,
        camera_alt_meters=camera_alt_meters,
        heading_deg=heading_deg,
        pitch_deg=pitch_deg,
        roll_deg=roll_deg,
        fov_deg=fov_deg,
        viewport_width=width,
        viewport_height=height,
        template=template_enum,
        anchors=anchor_models,
        horizon_ratio=horizon_ratio,
    )

    # 7. Run enhancement if requested
    enhanced_artifact: ArtifactInfo | None = None
    enhancement_ms: int | None = None
    status = "completed_with_warnings" if warnings else "completed"

    if enhancement_enabled:
        enhancement_start = time.monotonic()
        prompt = build_enhancement_prompt(enhancement_prompt)
        try:
            enhancement_result = await _enhance_preview(
                raw_image_path=render_result.image_path,
                output_path=preview_dir / "enhanced.png",
                prompt=prompt,
                api_key=settings.gemini_api_key,
                model=settings.gemini_image_model,
            )
            enhanced_bytes = enhancement_result.image_path.read_bytes()
            save_artifact(preview_dir, "enhanced", enhanced_bytes)
            enhanced_artifact = ArtifactInfo(
                local_path=str(preview_dir / "enhanced.png"),
                relative_url=artifact_url(preview_id, "enhanced"),
                width=width,
                height=height,
            )
            enhancement_ms = int((time.monotonic() - enhancement_start) * 1000)
        except EnhancementNotConfiguredError:
            status = "completed_with_warnings"
            warnings.append(PreviewWarningItem(
                code="enhancement_not_configured",
                message="Enhancement is not configured. Set GEMINI_API_KEY and GEMINI_IMAGE_MODEL.",
            ))
        except EnhancementError as e:
            status = "completed_with_warnings"
            warnings.append(PreviewWarningItem(
                code="enhancement_failed",
                message=f"Enhancement failed: {e}",
            ))
            enhancement_ms = int((time.monotonic() - enhancement_start) * 1000)

    # 8. Build metadata
    compass = _heading_to_compass(heading_deg)

    camera_metadata = {
        "lat": camera_lat,
        "lng": camera_lng,
        "alt_meters": camera_alt_meters,
        "heading_deg": heading_deg,
        "pitch_deg": pitch_deg,
        "roll_deg": roll_deg,
        "fov_deg": fov_deg,
        "compass_direction": compass,
    }

    location_metadata = {
        "scene_center": {"lat": scene_center_lat, "lng": scene_center_lng},
        "radius_meters": scene_radius_meters,
        "google_maps_url": (
            f"https://www.google.com/maps/search/?api=1"
            f"&query={scene_center_lat},{scene_center_lng}"
        ),
        "geo_uri": f"geo:{scene_center_lat},{scene_center_lng}",
    }

    scene_metadata = {
        "scene_id": scene_id,
        "scene_type": scene_type,
        "scene_summary": scene_summary,
        "feature_ids": feature_ids,
    }

    composition_metadata = {
        "target": {
            "template": target_template,
            "subject_label": subject_label,
            "horizon_ratio": horizon_ratio,
        },
        "verified": (
            verification.model_dump()
            if hasattr(verification, "model_dump")
            else verification
        ),
    }

    scene_type_label = scene_type or "terrain"
    template_label = target_template.replace("_", "-")
    summary_text = (
        f"{scene_type_label.capitalize()} preview facing {compass} at "
        f"{heading_deg:.0f} degrees with {template_label} framing."
    )

    total_ms = int((time.monotonic() - start_time) * 1000)

    timings = {
        "render": render_ms,
        "enhancement": enhancement_ms,
        "total": total_ms,
    }

    # 9. Save manifest
    manifest_data = {
        "id": preview_id,
        "status": status,
        "warnings": [{"code": w.code, "message": w.message} for w in warnings],
        "raw_artifact": {
            "local_path": raw_artifact.local_path,
            "relative_url": raw_artifact.relative_url,
            "width": raw_artifact.width,
            "height": raw_artifact.height,
        },
        "timings_ms": timings,
    }
    if enhanced_artifact:
        manifest_data["enhanced_artifact"] = {
            "local_path": enhanced_artifact.local_path,
            "relative_url": enhanced_artifact.relative_url,
            "width": enhanced_artifact.width,
            "height": enhanced_artifact.height,
        }
    save_manifest(preview_dir, manifest_data)

    return PreviewPipelineResult(
        preview_id=preview_id,
        status=status,
        warnings=warnings,
        raw_artifact=raw_artifact,
        enhanced_artifact=enhanced_artifact,
        camera_metadata=camera_metadata,
        location_metadata=location_metadata,
        scene_metadata=scene_metadata,
        composition_metadata=composition_metadata,
        summary=summary_text,
        timings_ms=timings,
        manifest_path=str(preview_dir / "manifest.json"),
        verification=(
            verification.model_dump()
            if hasattr(verification, "model_dump")
            else verification
        ),
    )
