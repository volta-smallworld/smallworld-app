"""Tests for MCP server tools and resources."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

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
