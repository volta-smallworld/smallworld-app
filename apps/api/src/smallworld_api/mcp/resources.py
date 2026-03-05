"""MCP resources: server-info and usage-guidance."""

from __future__ import annotations

import json

from smallworld_api.config import settings
from smallworld_api.mcp.server import mcp


@mcp.resource("smallworld://server-info")
def server_info() -> str:
    """Server capabilities and configuration."""
    info = {
        "name": "Smallworld MCP Server",
        "version": "1.1.0",
        "transports": ["stdio", "streamable-http"],
        "tools": [
            "terrain_analyze_area",
            "terrain_find_viewpoints",
            "preview_render_pose",
            "terrain_point_context",
        ],
        "terrain_defaults": {
            "zoom": settings.default_terrarium_zoom,
            "max_tiles_per_request": settings.max_tiles_per_request,
            "grid_size": 128,
        },
        "viewpoint_defaults": {
            "max_viewpoints": settings.viewpoint_max_returned,
            "max_per_scene": settings.viewpoint_max_per_scene,
            "fov_degrees": settings.viewpoint_default_fov_degrees,
        },
        "preview_capabilities": {
            "renderer_configured": bool(settings.preview_renderer_base_url),
            "enhancement_configured": bool(settings.gemini_api_key and settings.gemini_image_model),
            "enhancement_model": settings.gemini_image_model or None,
            "inline_images_supported": True,
            "artifact_url_base_configured": bool(settings.preview_public_base_url),
        },
    }
    return json.dumps(info, indent=2)


@mcp.resource("smallworld://usage-guidance")
def usage_guidance() -> str:
    """Agent workflow guidance for using Smallworld tools."""
    guidance = {
        "workflow": [
            {
                "step": 1,
                "tool": "terrain_analyze_area",
                "purpose": "Analyze terrain around a location to discover features, hotspots, and scenes.",
                "notes": "Start here to understand what the terrain looks like.",
            },
            {
                "step": 2,
                "tool": "terrain_find_viewpoints",
                "purpose": "Generate ranked camera viewpoints for the analyzed terrain.",
                "notes": (
                    "Each viewpoint includes a preview_input object that can be "
                    "passed directly to preview_render_pose."
                ),
            },
            {
                "step": 3,
                "tool": "preview_render_pose",
                "purpose": "Render a preview image from a specific camera pose.",
                "notes": (
                    "Use viewpoints[n].preview_input from step 2 as the input. "
                    "The camera, scene, and composition fields are all included. "
                    "Optionally override viewport dimensions or enhancement settings."
                ),
            },
            {
                "step": "optional",
                "tool": "terrain_point_context",
                "purpose": "Get precise ground elevation at a point and check camera AGL safety.",
                "notes": (
                    "Use this to verify a camera is not underground before rendering. "
                    "Pass camera_altitude_meters to get AGL clearance. "
                    "Also returns local slope, curvature, and relief context."
                ),
            },
        ],
        "tips": [
            "Viewpoints are ranked by a multi-factor beauty score. Higher scores are better.",
            "preview_input is designed to be passed directly to preview_render_pose without transformation.",
            "Enhancement requires Gemini API credentials. If not configured, you still get the raw render.",
            "Compositions use snake_case: rule_of_thirds, golden_ratio, leading_line, symmetry.",
            "preview_render_pose can render without anchors; missing anchor ids and normalized positions are inferred.",
            "preview_render_pose returns metadata by default. Set include_images=true to include base64 image data in the tool response. The chat UI renders images via proxy routes /api/previews/{id}/raw and /api/previews/{id}/enhanced — not from inline base64 data.",
            "Use terrain_point_context to check whether a camera pose is underground before rendering. Negative camera_agl_meters means the camera is inside terrain.",
            "Terrain tools automatically reduce zoom when a large radius would exceed the tile cap. Check zoom_used in the response.",
            "Craft a scene-specific enhancement prompt based on the terrain context (lighting, season, atmosphere, time of day). System guardrails protecting terrain fidelity are prepended automatically — your prompt only needs creative direction.",
            "Enhancement requires GEMINI_API_KEY. Without a custom prompt the default creative prompt (golden hour, cinematic grading) is used.",
        ],
    }
    return json.dumps(guidance, indent=2)
