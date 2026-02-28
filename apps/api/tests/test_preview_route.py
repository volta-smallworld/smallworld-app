from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from smallworld_api.main import app
from smallworld_api.services.preview_enhancement import (
    EnhancementError,
    EnhancementNotConfiguredError,
    EnhancementResult,
)
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
    "viewport": {"width": 1536, "height": 1024},
    "scene": {
        "center": {"lat": 39.7392, "lng": -104.9903},
        "radiusMeters": 5000,
        "sceneId": "scene-1",
        "sceneType": "peak-water",
        "sceneSummary": "Summit overlooking water feature",
        "featureIds": ["peak-1", "water-1"],
    },
    "composition": {
        "targetTemplate": "rule_of_thirds",
        "subjectLabel": "primary summit",
        "horizonRatio": 0.33,
        "anchors": [
            {
                "id": "peak-1",
                "label": "primary summit",
                "lat": 39.742,
                "lng": -104.981,
                "altMeters": 2180,
                "desiredNormalizedX": 0.66,
                "desiredNormalizedY": 0.38,
            }
        ],
    },
    "enhancement": {"enabled": True, "prompt": "Ultra-realistic landscape."},
}


def _mock_render_result():
    return RenderResult(image_path=Path("/tmp/test/raw.png"), frame_state={})


def _mock_enhancement_result():
    return EnhancementResult(
        image_path=Path("/tmp/test/enhanced.png"), model_used="test-model"
    )


def _patch_all():
    """Return a stack of patches for the route's dependencies."""
    return [
        patch(
            "smallworld_api.routes.previews.render_preview",
            new_callable=AsyncMock,
            return_value=_mock_render_result(),
        ),
        patch(
            "smallworld_api.routes.previews.enhance_preview",
            new_callable=AsyncMock,
            return_value=_mock_enhancement_result(),
        ),
        patch(
            "smallworld_api.routes.previews.ensure_preview_dir",
            return_value=Path("/tmp/test"),
        ),
        patch("smallworld_api.routes.previews.save_artifact"),
        patch("smallworld_api.routes.previews.save_manifest"),
        patch("smallworld_api.routes.previews.save_request"),
        patch("smallworld_api.routes.previews.cleanup_expired"),
        patch(
            "smallworld_api.routes.previews.generate_preview_id",
            return_value="preview_test123",
        ),
        patch.object(Path, "read_bytes", return_value=b"fakepng"),
    ]


def _apply_patches(patches):
    mocks = [p.start() for p in patches]
    return mocks


def _stop_patches(patches):
    for p in patches:
        p.stop()


def test_render_success_with_enhancement():
    patches = _patch_all()
    _apply_patches(patches)
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["rawImage"] is not None
        assert body["rawImage"]["url"].startswith("/api/v1/previews/")
        assert body["enhancedImage"] is not None
        assert body["enhancedImage"]["url"].startswith("/api/v1/previews/")
        assert isinstance(body["metadata"]["camera"]["compassDirection"], str)
        assert "39.7392" in body["metadata"]["location"]["googleMapsUrl"]
        assert body["metadata"]["composition"]["target"]["template"] == "rule_of_thirds"
    finally:
        _stop_patches(patches)


def test_render_success_without_enhancement():
    req = {**VALID_REQUEST, "enhancement": {"enabled": False}}
    patches = _patch_all()
    _apply_patches(patches)
    try:
        resp = client.post("/api/v1/previews/render", json=req)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["rawImage"] is not None
        assert body["enhancedImage"] is None
    finally:
        _stop_patches(patches)


def test_render_default_viewport():
    req = {k: v for k, v in VALID_REQUEST.items() if k != "viewport"}
    patches = _patch_all()
    _apply_patches(patches)
    try:
        resp = client.post("/api/v1/previews/render", json=req)
        assert resp.status_code == 200
    finally:
        _stop_patches(patches)


def test_invalid_pitch():
    req = {**VALID_REQUEST}
    req["camera"] = {**req["camera"], "pitchDeg": 95}
    resp = client.post("/api/v1/previews/render", json=req)
    assert resp.status_code == 422


def test_invalid_fov():
    req = {**VALID_REQUEST}
    req["camera"] = {**req["camera"], "fovDeg": 200}
    resp = client.post("/api/v1/previews/render", json=req)
    assert resp.status_code == 422


def test_invalid_radius():
    req = {**VALID_REQUEST}
    req["scene"] = {**req["scene"], "radiusMeters": 100}
    resp = client.post("/api/v1/previews/render", json=req)
    assert resp.status_code == 422


def test_enhancement_failure_still_returns_200():
    patches = _patch_all()
    mocks = _apply_patches(patches)
    # mocks[1] is enhance_preview
    mocks[1].side_effect = EnhancementError("Failed")
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()
        assert body["rawImage"] is not None
        assert body["enhancedImage"] is None
        assert body["status"] == "completed_with_warnings"
        codes = [w["code"] for w in body["warnings"]]
        assert "enhancement_failed" in codes
    finally:
        _stop_patches(patches)


def test_enhancement_not_configured_returns_200():
    patches = _patch_all()
    mocks = _apply_patches(patches)
    mocks[1].side_effect = EnhancementNotConfiguredError("Not configured")
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed_with_warnings"
        codes = [w["code"] for w in body["warnings"]]
        assert "enhancement_not_configured" in codes
    finally:
        _stop_patches(patches)


@patch(
    "smallworld_api.routes.previews.render_preview",
    new_callable=AsyncMock,
    side_effect=RenderTimeoutError("timeout"),
)
@patch("smallworld_api.routes.previews.ensure_preview_dir", return_value=Path("/tmp/test"))
@patch("smallworld_api.routes.previews.save_request")
@patch("smallworld_api.routes.previews.cleanup_expired")
@patch(
    "smallworld_api.routes.previews.generate_preview_id",
    return_value="preview_test123",
)
def test_render_timeout_returns_504(_gen, _clean, _save, _dir, _render):
    resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
    assert resp.status_code == 504


@patch(
    "smallworld_api.routes.previews.render_preview",
    new_callable=AsyncMock,
    side_effect=RenderError("crash"),
)
@patch("smallworld_api.routes.previews.ensure_preview_dir", return_value=Path("/tmp/test"))
@patch("smallworld_api.routes.previews.save_request")
@patch("smallworld_api.routes.previews.cleanup_expired")
@patch(
    "smallworld_api.routes.previews.generate_preview_id",
    return_value="preview_test123",
)
def test_render_error_returns_502(_gen, _clean, _save, _dir, _render):
    resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
    assert resp.status_code == 502


def test_render_backend_not_configured():
    from smallworld_api.config import settings

    original = settings.preview_renderer_base_url
    settings.preview_renderer_base_url = ""
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 503
    finally:
        settings.preview_renderer_base_url = original
