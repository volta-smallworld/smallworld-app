"""MCP tool: preview_render_pose."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import Image as McpImage

from smallworld_api.config import settings
from smallworld_api.mcp.schemas import (
    McpCameraPose,
    McpEnhancementOptions,
    McpPreviewComposition,
    McpPreviewScene,
    McpViewportSpec,
    PreviewArtifactRef,
    PreviewRenderPoseInput,
    PreviewRenderPoseResult,
    PreviewWarning,
    composition_from_mcp,
)
from smallworld_api.mcp.server import mcp
from smallworld_api.services.preview_renderer import RenderError, RenderTimeoutError
from smallworld_api.services.previews import (
    PreviewRendererNotConfiguredError,
    render_preview_pipeline,
)

logger = logging.getLogger(__name__)


@mcp.tool()
async def preview_render_pose(
    camera: dict,
    scene: dict,
    composition: dict,
    viewport: dict | None = None,
    enhancement: dict | None = None,
    include_images: bool = False,
) -> dict | ToolResult:
    """Render a preview image from an explicit camera pose.

    Use viewpoints[n].preview_input from terrain_find_viewpoints as input.
    The camera, scene, and composition fields are required; viewport and
    enhancement are optional overrides.

    Args:
        camera: Camera pose with position (lat, lng, alt_meters), heading_deg, pitch_deg, roll_deg, fov_deg
        scene: Scene context with center (lat, lng), radius_meters, scene_id, scene_type
        composition: Composition with target_template, subject_label, horizon_ratio, anchors
        viewport: Optional viewport override with width and height
        enhancement: Optional enhancement override with enabled flag and prompt.
            The prompt field is for **creative direction only** — describe lighting,
            atmosphere, season, time of day, and mood. Terrain-fidelity guardrails
            are prepended automatically so the prompt should NOT include instructions
            about preserving terrain or geography.
    """
    # Parse and validate input via Pydantic
    cam = McpCameraPose(**camera)
    sc = McpPreviewScene(**scene)
    comp = McpPreviewComposition(**composition)
    vp = McpViewportSpec(**(viewport or {}))
    enh = McpEnhancementOptions(**(enhancement or {}))

    # Convert MCP composition to REST format for the shared pipeline
    rest_template = composition_from_mcp(comp.target_template.value)

    # Convert anchors to dicts with REST-compatible field names
    anchors_dicts = None
    if comp.anchors:
        anchors_dicts = [
            {
                "id": a.id or f"anchor-{idx + 1}",
                "label": a.label,
                "lat": a.lat,
                "lng": a.lng,
                "alt_meters": a.alt_meters,
                "desired_normalized_x": a.desired_normalized_x,
                "desired_normalized_y": a.desired_normalized_y,
            }
            for idx, a in enumerate(comp.anchors)
        ]

    # ── Delegation mode: POST to API service when api_internal_url is set ──
    if settings.api_internal_url:
        return await _delegate_to_api(
            cam=cam, sc=sc, comp=comp, vp=vp, enh=enh,
            rest_template=rest_template,
            anchors_dicts=anchors_dicts,
            include_images=include_images,
        )

    # ── Local mode: call render pipeline in-process ──
    try:
        result = await render_preview_pipeline(
            camera_lat=cam.position.lat,
            camera_lng=cam.position.lng,
            camera_alt_meters=cam.position.alt_meters,
            heading_deg=cam.heading_deg,
            pitch_deg=cam.pitch_deg,
            roll_deg=cam.roll_deg,
            fov_deg=cam.fov_deg,
            viewport_width=vp.width,
            viewport_height=vp.height,
            scene_center_lat=sc.center.get("lat", 0),
            scene_center_lng=sc.center.get("lng", 0),
            scene_radius_meters=sc.radius_meters,
            scene_id=sc.scene_id,
            scene_type=sc.scene_type,
            scene_summary=sc.scene_summary,
            feature_ids=sc.feature_ids,
            target_template=rest_template,
            subject_label=comp.subject_label,
            horizon_ratio=comp.horizon_ratio,
            anchors=anchors_dicts,
            enhancement_enabled=enh.enabled,
            enhancement_prompt=enh.prompt,
        )
    except PreviewRendererNotConfiguredError:
        raise RuntimeError(
            "Preview renderer is not configured. "
            "Set PREVIEW_RENDERER_BASE_URL to enable rendering."
        )
    except RenderTimeoutError:
        raise RuntimeError("Preview render timed out. Try again or use a simpler scene.")
    except RenderError as e:
        raise RuntimeError(f"Preview render failed: {e}")

    return _build_output(result, include_images)


async def _delegate_to_api(
    *,
    cam: McpCameraPose,
    sc: McpPreviewScene,
    comp: McpPreviewComposition,
    vp: McpViewportSpec,
    enh: McpEnhancementOptions,
    rest_template: str,
    anchors_dicts: list[dict] | None,
    include_images: bool,
) -> dict | ToolResult:
    """Delegate preview rendering to the API service via HTTP."""
    # Build REST-compatible anchors (camelCase)
    rest_anchors = None
    if anchors_dicts:
        rest_anchors = [
            {
                "id": a["id"],
                "label": a.get("label"),
                "lat": a["lat"],
                "lng": a["lng"],
                "altMeters": a.get("alt_meters", 0),
                "desiredNormalizedX": a.get("desired_normalized_x", 0.5),
                "desiredNormalizedY": a.get("desired_normalized_y", 0.5),
            }
            for a in anchors_dicts
        ]

    payload = {
        "camera": {
            "position": {
                "lat": cam.position.lat,
                "lng": cam.position.lng,
                "altMeters": cam.position.alt_meters,
            },
            "headingDeg": cam.heading_deg,
            "pitchDeg": cam.pitch_deg,
            "rollDeg": cam.roll_deg,
            "fovDeg": cam.fov_deg,
        },
        "viewport": {"width": vp.width, "height": vp.height},
        "scene": {
            "center": sc.center,
            "radiusMeters": sc.radius_meters,
            "sceneId": sc.scene_id,
            "sceneType": sc.scene_type,
            "sceneSummary": sc.scene_summary,
            "featureIds": sc.feature_ids,
        },
        "composition": {
            "targetTemplate": rest_template,
            "subjectLabel": comp.subject_label,
            "horizonRatio": comp.horizon_ratio,
            "anchors": rest_anchors,
        },
        "enhancement": {
            "enabled": enh.enabled,
            "prompt": enh.prompt,
        },
    }

    url = f"{settings.api_internal_url.rstrip('/')}/api/v1/previews/render"
    timeout = settings.preview_render_timeout_seconds + 30  # extra margin for delegation

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
    except httpx.TimeoutException:
        raise RuntimeError("Preview render timed out (API delegation). Try again or use a simpler scene.")
    except httpx.ConnectError as e:
        raise RuntimeError(f"Could not reach API service at {settings.api_internal_url}: {e}")

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise RuntimeError(f"API preview render failed (HTTP {resp.status_code}): {detail}")

    data = resp.json()
    public_base = settings.preview_public_base_url

    raw_ref = PreviewArtifactRef(
        local_path="",
        url=f"{public_base}{data['rawImage']['url']}" if public_base and data.get("rawImage") else None,
        width=data["rawImage"]["width"] if data.get("rawImage") else 0,
        height=data["rawImage"]["height"] if data.get("rawImage") else 0,
    )

    enhanced_ref = None
    if data.get("enhancedImage"):
        enhanced_ref = PreviewArtifactRef(
            local_path="",
            url=f"{public_base}{data['enhancedImage']['url']}" if public_base else None,
            width=data["enhancedImage"]["width"],
            height=data["enhancedImage"]["height"],
        )

    warnings = [
        PreviewWarning(code=w["code"], message=w["message"])
        for w in data.get("warnings", [])
    ]

    output = PreviewRenderPoseResult(
        id=data["id"],
        status=data["status"],
        warnings=warnings,
        raw_image=raw_ref,
        enhanced_image=enhanced_ref,
        metadata=data.get("metadata", {}),
        timings_ms=data.get("timingsMs", {}),
        manifest_path="",
    )

    # In delegation mode, include_images fetches from the API's artifact URL
    if not include_images:
        return output.model_dump()

    output_payload = output.model_dump()
    content_items: list = [json.dumps(output_payload, indent=2, default=str)]

    if raw_ref.url:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                img_resp = await client.get(f"{settings.api_internal_url.rstrip('/')}{data['rawImage']['url']}")
                if img_resp.status_code == 200:
                    content_items.append(McpImage(data=img_resp.content, format="png"))
        except Exception:
            logger.warning("Could not fetch raw image for inline display")

    if enhanced_ref and enhanced_ref.url:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                img_resp = await client.get(f"{settings.api_internal_url.rstrip('/')}{data['enhancedImage']['url']}")
                if img_resp.status_code == 200:
                    content_items.append(McpImage(data=img_resp.content, format="png"))
        except Exception:
            logger.warning("Could not fetch enhanced image for inline display")

    return ToolResult(
        content=content_items,
        structured_content={"result": output_payload},
    )


def _build_output(result, include_images: bool) -> dict | ToolResult:
    """Build MCP output from a local pipeline result."""
    public_base = settings.preview_public_base_url

    raw_ref = PreviewArtifactRef(
        local_path=result.raw_artifact.local_path,
        url=f"{public_base}{result.raw_artifact.relative_url}" if public_base else None,
        width=result.raw_artifact.width,
        height=result.raw_artifact.height,
    )

    enhanced_ref = None
    if result.enhanced_artifact:
        enhanced_ref = PreviewArtifactRef(
            local_path=result.enhanced_artifact.local_path,
            url=f"{public_base}{result.enhanced_artifact.relative_url}" if public_base else None,
            width=result.enhanced_artifact.width,
            height=result.enhanced_artifact.height,
        )

    warnings = [
        PreviewWarning(code=w.code, message=w.message)
        for w in result.warnings
    ]

    output = PreviewRenderPoseResult(
        id=result.preview_id,
        status=result.status,
        warnings=warnings,
        raw_image=raw_ref,
        enhanced_image=enhanced_ref,
        metadata={
            "camera": result.camera_metadata,
            "location": result.location_metadata,
            "scene": result.scene_metadata,
            "composition": result.composition_metadata,
            "summary": result.summary,
        },
        timings_ms=result.timings_ms,
        manifest_path=result.manifest_path,
    )

    if not include_images:
        return output.model_dump()

    output_payload = output.model_dump()
    content_items: list = []
    content_items.append(json.dumps(output_payload, indent=2, default=str))

    content_items.append(
        McpImage(data=Path(result.raw_artifact.local_path).read_bytes(), format="png")
    )
    if result.enhanced_artifact:
        content_items.append(
            McpImage(
                data=Path(result.enhanced_artifact.local_path).read_bytes(),
                format="png",
            )
        )

    return ToolResult(
        content=content_items,
        structured_content={"result": output_payload},
    )
