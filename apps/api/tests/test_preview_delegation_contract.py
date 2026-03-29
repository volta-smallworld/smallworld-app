"""Tests for API contract assumptions used by the web delegation layer.

Validates response shapes, error formats, and status codes that the
web preview route depends on when delegating to the API pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from smallworld_api.config import settings
from smallworld_api.main import app
from smallworld_api.services.preview_renderer import (
    RenderError,
    RenderResult,
    RenderTimeoutError,
)

client = TestClient(app)

VALID_REQUEST = {
    "camera": {
        "position": {"lat": 39.7392, "lng": -104.9903, "altMeters": 2450},
        "headingDeg": 72.0,
        "pitchDeg": -18.0,
        "rollDeg": 0.0,
        "fovDeg": 50.0,
    },
    "viewport": {"width": 1280, "height": 720},
    "scene": {
        "center": {"lat": 39.7392, "lng": -104.9903},
        "radiusMeters": 5000,
    },
    "composition": {"targetTemplate": "custom"},
    "enhancement": {"enabled": False},
}

_SVC = "smallworld_api.services.previews"


def _mock_render_result():
    return RenderResult(image_path=Path("/tmp/test/raw.png"), frame_state={})


def _patch_pipeline():
    return [
        patch(
            f"{_SVC}._render_preview",
            new_callable=AsyncMock,
            return_value=_mock_render_result(),
        ),
        patch(
            f"{_SVC}._enhance_preview",
            new_callable=AsyncMock,
        ),
        patch(
            f"{_SVC}.ensure_preview_dir",
            return_value=Path("/tmp/test"),
        ),
        patch(f"{_SVC}.save_artifact"),
        patch(f"{_SVC}.save_manifest"),
        patch(f"{_SVC}.save_request"),
        patch(f"{_SVC}.cleanup_expired"),
        patch(
            f"{_SVC}.generate_preview_id",
            return_value="preview_contract_test",
        ),
        patch.object(Path, "read_bytes", return_value=b"fakepng"),
    ]


def _apply_patches(patches):
    return [p.start() for p in patches]


def _stop_patches(patches):
    for p in patches:
        p.stop()


# ── Response shape: rawImage.url follows artifact pattern ────────────────


def test_render_response_raw_image_url_pattern():
    """rawImage.url must match /api/v1/previews/{id}/artifacts/raw."""
    patches = _patch_pipeline()
    _apply_patches(patches)
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()
        assert body["rawImage"] is not None
        url = body["rawImage"]["url"]
        assert re.match(r"/api/v1/previews/[^/]+/artifacts/raw", url), f"Unexpected URL: {url}"
    finally:
        _stop_patches(patches)


def test_render_response_has_required_fields():
    """Render response must include id, status, rawImage, metadata, timingsMs."""
    patches = _patch_pipeline()
    _apply_patches(patches)
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert "status" in body
        assert "rawImage" in body
        assert "metadata" in body
        assert "timingsMs" in body
    finally:
        _stop_patches(patches)


# ── Error responses include detail field ─────────────────────────────────


def test_503_includes_detail():
    """503 from renderer not configured must include detail field."""
    orig = settings.preview_renderer_base_url
    settings.preview_renderer_base_url = ""
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 503
        body = resp.json()
        assert "detail" in body
    finally:
        settings.preview_renderer_base_url = orig


def test_504_includes_detail():
    """504 from render timeout must include detail field."""
    orig_google = settings.google_maps_api_key
    orig_ion = settings.cesium_ion_token
    settings.google_maps_api_key = ""
    settings.cesium_ion_token = ""

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mocks[0].side_effect = RenderTimeoutError("test timeout")
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 504
        body = resp.json()
        assert "detail" in body
    finally:
        settings.google_maps_api_key = orig_google
        settings.cesium_ion_token = orig_ion
        _stop_patches(patches)


def test_502_includes_detail():
    """502 from render failure must include detail field."""
    orig_google = settings.google_maps_api_key
    orig_ion = settings.cesium_ion_token
    settings.google_maps_api_key = ""
    settings.cesium_ion_token = ""

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mocks[0].side_effect = RenderError("test crash")
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 502
        body = resp.json()
        assert "detail" in body
    finally:
        settings.google_maps_api_key = orig_google
        settings.cesium_ion_token = orig_ion
        _stop_patches(patches)


# ── Minimal delegation request shape is accepted ─────────────────────────


def test_minimal_delegation_request_accepted():
    """The minimal request shape used by web delegation must be accepted."""
    patches = _patch_pipeline()
    _apply_patches(patches)
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
    finally:
        _stop_patches(patches)
