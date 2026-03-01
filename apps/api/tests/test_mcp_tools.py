"""Tests for MCP server tools and resources."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from fastmcp.tools.tool import ToolResult

from smallworld_api.mcp.schemas import (
    McpCompositionType,
    TerrainAnalyzeAreaInput,
    TerrainFindViewpointsInput,
    PreviewRenderPoseInput,
    McpCameraPose,
    McpGeoPosition,
    McpPreviewScene,
    McpPreviewComposition,
    McpPreviewAnchor,
    composition_to_mcp,
    composition_from_mcp,
)
from smallworld_api.services.previews import (
    ArtifactInfo,
    PreviewPipelineResult,
    PreviewRendererNotConfiguredError,
    PreviewWarningItem,
)
from smallworld_api.services.preview_renderer import RenderError, RenderTimeoutError


# ── Schema tests ─────────────────────────────────────────────────────────


class TestCompositionMapping:
    def test_to_mcp(self):
        assert composition_to_mcp("ruleOfThirds") == McpCompositionType.rule_of_thirds
        assert composition_to_mcp("goldenRatio") == McpCompositionType.golden_ratio
        assert composition_to_mcp("leadingLine") == McpCompositionType.leading_line
        assert composition_to_mcp("symmetry") == McpCompositionType.symmetry

    def test_from_mcp(self):
        assert composition_from_mcp("rule_of_thirds") == "ruleOfThirds"
        assert composition_from_mcp("golden_ratio") == "goldenRatio"
        assert composition_from_mcp("leading_line") == "leadingLine"
        assert composition_from_mcp("symmetry") == "symmetry"

    def test_roundtrip(self):
        for rest_val in ("ruleOfThirds", "goldenRatio", "leadingLine", "symmetry"):
            mcp_val = composition_to_mcp(rest_val)
            assert composition_from_mcp(mcp_val.value) == rest_val


class TestTerrainAnalyzeAreaInput:
    def test_valid(self):
        inp = TerrainAnalyzeAreaInput(lat=39.7, lng=-105.0, radius_meters=5000)
        assert inp.lat == 39.7
        assert inp.include_elevations is False

    def test_include_elevations(self):
        inp = TerrainAnalyzeAreaInput(lat=39.7, lng=-105.0, radius_meters=5000, include_elevations=True)
        assert inp.include_elevations is True

    def test_invalid_lat(self):
        with pytest.raises(Exception):
            TerrainAnalyzeAreaInput(lat=91.0, lng=-105.0, radius_meters=5000)


class TestTerrainFindViewpointsInput:
    def test_defaults(self):
        inp = TerrainFindViewpointsInput(lat=39.7, lng=-105.0, radius_meters=5000)
        assert inp.max_viewpoints == 12
        assert inp.max_per_scene == 3
        assert inp.include_preview_input is True
        assert inp.compositions is None

    def test_with_compositions(self):
        inp = TerrainFindViewpointsInput(
            lat=39.7, lng=-105.0, radius_meters=5000,
            compositions=[McpCompositionType.rule_of_thirds],
        )
        assert len(inp.compositions) == 1


class TestPreviewRenderPoseInput:
    def test_full_input(self):
        inp = PreviewRenderPoseInput(
            camera=McpCameraPose(
                position=McpGeoPosition(lat=39.7, lng=-105.0, alt_meters=2400),
                heading_deg=113.5,
                pitch_deg=-8.4,
            ),
            scene=McpPreviewScene(
                center={"lat": 39.7392, "lng": -104.9903},
                radius_meters=5000,
                scene_id="scene-1",
                scene_type="peak-ridge",
            ),
            composition=McpPreviewComposition(
                target_template=McpCompositionType.rule_of_thirds,
                anchors=[
                    McpPreviewAnchor(
                        id="peak-1", lat=39.742, lng=-104.981,
                        alt_meters=2180, desired_normalized_x=0.667,
                        desired_normalized_y=0.333,
                    ),
                ],
            ),
        )
        assert inp.camera.position.alt_meters == 2400
        assert inp.composition.target_template == McpCompositionType.rule_of_thirds


# ── Adapter tests ────────────────────────────────────────────────────────


class TestAdapters:
    def test_convert_viewpoint(self):
        from smallworld_api.mcp.adapters import convert_viewpoint

        vp = {
            "id": "vp-1",
            "sceneId": "scene-1",
            "sceneType": "peak-ridge",
            "composition": "ruleOfThirds",
            "camera": {
                "lat": 39.75,
                "lng": -105.0,
                "altitudeMeters": 2500.0,
                "headingDegrees": 113.5,
                "pitchDegrees": -8.4,
                "rollDegrees": 0,
                "fovDegrees": 55,
            },
            "targets": [
                {"featureId": "peak-1", "role": "primary", "xNorm": 0.667, "yNorm": 0.333},
            ],
            "distanceMetersApprox": 3200.0,
            "score": 0.78,
            "scoreBreakdown": {
                "viewshedRichness": 0.85,
                "terrainEntropy": 0.72,
                "skylineFractal": 0.9,
                "prospectRefuge": 0.6,
                "depthLayering": 0.7,
                "mystery": 0.5,
                "waterVisibility": 0.0,
            },
            "validation": {
                "clearanceMeters": 120.3,
                "visibleTargetIds": ["peak-1"],
            },
        }

        scene_dict = {
            "id": "scene-1",
            "type": "peak-ridge",
            "center": {"lat": 39.74, "lng": -104.99},
            "summary": "Peak with ridge",
            "featureIds": ["peak-1"],
        }

        feature_index = {
            "peak-1": {
                "id": "peak-1",
                "center": {"lat": 39.742, "lng": -104.981},
                "elevationMeters": 2180.0,
                "score": 0.9,
            },
        }

        result = convert_viewpoint(
            vp,
            scene_dict=scene_dict,
            feature_index=feature_index,
            request_radius_meters=5000,
            include_preview_input=True,
        )

        assert result.id == "vp-1"
        assert result.scene == "scene-1"
        assert result.composition == McpCompositionType.rule_of_thirds
        assert result.camera.position.alt_meters == 2500.0
        assert result.camera.heading_deg == 113.5
        assert result.score == 0.78
        assert result.score_breakdown.viewshed_richness == 0.85
        assert result.validation.clearance_meters == 120.3
        assert result.preview_input is not None
        assert result.preview_input.scene.scene_id == "scene-1"
        assert result.preview_input.composition.target_template == McpCompositionType.rule_of_thirds

    def test_convert_viewpoint_without_preview(self):
        from smallworld_api.mcp.adapters import convert_viewpoint

        vp = {
            "id": "vp-1",
            "sceneId": "scene-1",
            "sceneType": "peak-ridge",
            "composition": "ruleOfThirds",
            "camera": {
                "lat": 39.75, "lng": -105.0, "altitudeMeters": 2500.0,
                "headingDegrees": 113.5, "pitchDegrees": -8.4,
                "rollDegrees": 0, "fovDegrees": 55,
            },
            "targets": [],
            "distanceMetersApprox": 3200.0,
            "score": 0.78,
            "scoreBreakdown": {},
            "validation": {"clearanceMeters": 120.3, "visibleTargetIds": []},
        }

        result = convert_viewpoint(
            vp,
            scene_dict={},
            feature_index={},
            request_radius_meters=5000,
            include_preview_input=False,
        )

        assert result.preview_input is None

    def test_convert_summary(self):
        from smallworld_api.mcp.adapters import convert_summary

        summary = {
            "sceneCount": 5,
            "eligibleSceneCount": 3,
            "candidatesGenerated": 12,
            "candidatesRejected": {"templateIneligible": 2, "noConvergence": 1},
            "returned": 9,
        }

        result = convert_summary(summary)
        assert result.scene_count == 5
        assert result.returned == 9


# ── Resource tests ───────────────────────────────────────────────────────


class TestResources:
    def test_server_info(self):
        from smallworld_api.mcp.resources import server_info

        info = json.loads(server_info())
        assert info["name"] == "Smallworld MCP Server"
        assert "terrain_analyze_area" in info["tools"]
        assert "terrain_find_viewpoints" in info["tools"]
        assert "preview_render_pose" in info["tools"]
        assert "terrain_defaults" in info
        assert "viewpoint_defaults" in info
        assert "preview_capabilities" in info

    def test_usage_guidance(self):
        from smallworld_api.mcp.resources import usage_guidance

        guidance = json.loads(usage_guidance())
        assert len(guidance["workflow"]) == 3
        assert guidance["workflow"][0]["tool"] == "terrain_analyze_area"
        assert guidance["workflow"][1]["tool"] == "terrain_find_viewpoints"
        assert guidance["workflow"][2]["tool"] == "preview_render_pose"


# ── Tool registration test ───────────────────────────────────────────────


class TestToolRegistration:
    async def test_server_has_three_tools(self):
        from smallworld_api.mcp.server import mcp

        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert "terrain_analyze_area" in tool_names
        assert "terrain_find_viewpoints" in tool_names
        assert "preview_render_pose" in tool_names

    async def test_server_has_two_resources(self):
        from smallworld_api.mcp.server import mcp

        resources = await mcp.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        assert "smallworld://server-info" in resource_uris
        assert "smallworld://usage-guidance" in resource_uris


# ── Preview render pose tool tests ──────────────────────────────────────


def _make_pipeline_result(
    tmp_dir: Path, *, with_enhanced: bool = False
) -> PreviewPipelineResult:
    """Build a minimal PreviewPipelineResult with real temp image files."""
    # Create a minimal 1x1 PNG for McpImage to read
    import struct
    import zlib

    def _minimal_png() -> bytes:
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
        ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
        raw_data = zlib.compress(b"\x00\x00\x00\x00")
        idat_crc = zlib.crc32(b"IDAT" + raw_data) & 0xFFFFFFFF
        idat = struct.pack(">I", len(raw_data)) + b"IDAT" + raw_data + struct.pack(">I", idat_crc)
        iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
        iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
        return sig + ihdr + idat + iend

    png_bytes = _minimal_png()

    raw_path = tmp_dir / "raw.png"
    raw_path.write_bytes(png_bytes)

    raw = ArtifactInfo(
        local_path=str(raw_path),
        relative_url="/api/v1/previews/abc123/artifacts/raw",
        width=1536,
        height=1024,
    )
    enhanced = None
    if with_enhanced:
        enh_path = tmp_dir / "enhanced.png"
        enh_path.write_bytes(png_bytes)
        enhanced = ArtifactInfo(
            local_path=str(enh_path),
            relative_url="/api/v1/previews/abc123/artifacts/enhanced",
            width=1536,
            height=1024,
        )
    return PreviewPipelineResult(
        preview_id="abc123",
        status="completed",
        warnings=[],
        raw_artifact=raw,
        enhanced_artifact=enhanced,
        camera_metadata={"lat": 39.7, "lng": -105.0, "heading_deg": 113.5},
        location_metadata={"scene_center": {"lat": 39.74, "lng": -104.99}},
        scene_metadata={"scene_id": "s1", "scene_type": "peak-ridge"},
        composition_metadata={"target": {"template": "ruleOfThirds"}},
        summary="Peak preview facing ESE",
        timings_ms={"render": 1200, "enhancement": None, "total": 1500},
        manifest_path=str(tmp_dir / "manifest.json"),
    )


# Shared tool kwargs matching the function signature
_TOOL_KWARGS = dict(
    camera={
        "position": {"lat": 39.7, "lng": -105.0, "alt_meters": 2400},
        "heading_deg": 113.5,
        "pitch_deg": -8.4,
    },
    scene={
        "center": {"lat": 39.74, "lng": -104.99},
        "radius_meters": 5000,
    },
    composition={
        "target_template": "rule_of_thirds",
    },
)


class TestPreviewRenderPoseTool:
    """Tests for the preview_render_pose MCP tool function."""

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    @patch("smallworld_api.mcp.tools_previews.settings")
    async def test_include_images_false_returns_dict(self, mock_settings, mock_pipeline, tmp_path):
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_settings.preview_public_base_url = "http://localhost:8080"
        mock_pipeline.return_value = _make_pipeline_result(tmp_path)

        result = await preview_render_pose(**_TOOL_KWARGS, include_images=False)

        assert isinstance(result, dict)
        assert result["id"] == "abc123"
        assert result["status"] == "completed"
        assert "raw.png" in result["raw_image"]["local_path"]
        assert result["raw_image"]["url"].startswith("http://localhost:8080")
        assert result["enhanced_image"] is None

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    @patch("smallworld_api.mcp.tools_previews.settings")
    async def test_include_images_true_returns_tool_result(self, mock_settings, mock_pipeline, tmp_path):
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_settings.preview_public_base_url = ""
        mock_pipeline.return_value = _make_pipeline_result(tmp_path)

        result = await preview_render_pose(**_TOOL_KWARGS, include_images=True)

        assert isinstance(result, ToolResult)
        assert result.structured_content is not None
        assert "result" in result.structured_content
        assert result.structured_content["result"]["id"] == "abc123"
        # Content should have JSON text + raw image
        assert len(result.content) >= 2

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    @patch("smallworld_api.mcp.tools_previews.settings")
    async def test_default_include_images_returns_dict(self, mock_settings, mock_pipeline, tmp_path):
        """Default (include_images omitted) should return metadata-only output."""
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_settings.preview_public_base_url = ""
        mock_pipeline.return_value = _make_pipeline_result(tmp_path)

        # Call without include_images — should default to False
        result = await preview_render_pose(**_TOOL_KWARGS)

        assert isinstance(result, dict)
        assert result["id"] == "abc123"
        assert result["raw_image"]["url"] is None

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    @patch("smallworld_api.mcp.tools_previews.settings")
    async def test_missing_anchor_fields_are_inferred(self, mock_settings, mock_pipeline, tmp_path):
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_settings.preview_public_base_url = ""
        mock_pipeline.return_value = _make_pipeline_result(tmp_path)

        tool_kwargs = {
            **_TOOL_KWARGS,
            "composition": {
                "target_template": "rule_of_thirds",
                "anchors": [
                    {
                        "lat": 39.74,
                        "lng": -104.99,
                        "alt_meters": 2500,
                    }
                ],
            },
        }
        result = await preview_render_pose(
            **tool_kwargs,
        )

        assert isinstance(result, dict)
        kwargs = mock_pipeline.await_args.kwargs
        assert kwargs["anchors"] == [
            {
                "id": "anchor-1",
                "label": None,
                "lat": 39.74,
                "lng": -104.99,
                "alt_meters": 2500,
                "desired_normalized_x": 0.5,
                "desired_normalized_y": 0.5,
            }
        ]

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    @patch("smallworld_api.mcp.tools_previews.settings")
    async def test_inline_with_enhanced_artifact(self, mock_settings, mock_pipeline, tmp_path):
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_settings.preview_public_base_url = ""
        mock_pipeline.return_value = _make_pipeline_result(tmp_path, with_enhanced=True)

        result = await preview_render_pose(**_TOOL_KWARGS, include_images=True)

        assert isinstance(result, ToolResult)
        # JSON text + raw image + enhanced image = 3 content blocks
        assert len(result.content) >= 3
        assert result.structured_content["result"]["enhanced_image"] is not None

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    async def test_error_renderer_not_configured(self, mock_pipeline):
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_pipeline.side_effect = PreviewRendererNotConfiguredError("not configured")

        with pytest.raises(RuntimeError, match="Preview renderer is not configured"):
            await preview_render_pose(**_TOOL_KWARGS)

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    async def test_error_render_timeout(self, mock_pipeline):
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_pipeline.side_effect = RenderTimeoutError("timed out")

        with pytest.raises(RuntimeError, match="timed out"):
            await preview_render_pose(**_TOOL_KWARGS)

    @patch("smallworld_api.mcp.tools_previews.render_preview_pipeline", new_callable=AsyncMock)
    async def test_error_render_failed(self, mock_pipeline):
        from smallworld_api.mcp.tools_previews import preview_render_pose

        mock_pipeline.side_effect = RenderError("renderer crashed")

        with pytest.raises(RuntimeError, match="Preview render failed: renderer crashed"):
            await preview_render_pose(**_TOOL_KWARGS)
