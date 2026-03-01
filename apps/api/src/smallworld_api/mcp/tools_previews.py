"""MCP tool: preview_render_pose."""

from __future__ import annotations

import json
import logging
from pathlib import Path

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

    # Build artifact refs with optional public URLs
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

    # Build content blocks: JSON text + inline image(s)
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

    # Return ToolResult with both content blocks and structured output
    # so FastMCP output-schema validation passes.
    return ToolResult(
        content=content_items,
        structured_content={"result": output_payload},
    )
