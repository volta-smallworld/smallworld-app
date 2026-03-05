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


# Patches now target the services.previews module where the functions
# are actually looked up at runtime (after the route→service refactor).
_SVC = "smallworld_api.services.previews"


def _patch_all():
    """Return a stack of patches for the service pipeline's dependencies."""
    return [
        patch(
            f"{_SVC}._render_preview",
            new_callable=AsyncMock,
            return_value=_mock_render_result(),
        ),
        patch(
            f"{_SVC}._enhance_preview",
            new_callable=AsyncMock,
            return_value=_mock_enhancement_result(),
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
    # mocks[1] is _enhance_preview
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


def test_render_retries_with_provider_fallback_and_returns_warning():
    from smallworld_api.config import settings

    original_google_key = settings.google_maps_api_key
    settings.google_maps_api_key = "test-google-key"

    patches = _patch_all()
    mocks = _apply_patches(patches)
    # First attempt (google_3d) fails, second attempt (osm) succeeds
    mocks[0].side_effect = [RenderTimeoutError("timeout"), _mock_render_result()]
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed_with_warnings"
        codes = [w["code"] for w in body["warnings"]]
        assert "render_provider_fallback" in codes
        assert mocks[0].await_count == 2
    finally:
        settings.google_maps_api_key = original_google_key
        _stop_patches(patches)


@patch(
    f"{_SVC}._render_preview",
    new_callable=AsyncMock,
    side_effect=RenderTimeoutError("timeout"),
)
@patch(f"{_SVC}.save_manifest")
@patch(f"{_SVC}.ensure_preview_dir", return_value=Path("/tmp/test"))
@patch(f"{_SVC}.save_request")
@patch(f"{_SVC}.cleanup_expired")
@patch(
    f"{_SVC}.generate_preview_id",
    return_value="preview_test123",
)
def test_render_timeout_returns_504_and_writes_failure_manifest(_gen, _clean, _save, _dir, mock_save_manifest, _render):
    from smallworld_api.config import settings

    original_google_key = settings.google_maps_api_key
    settings.google_maps_api_key = ""
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 504
        manifest = mock_save_manifest.call_args.args[1]
        assert manifest["status"] == "failed"
        assert manifest["error"]["type"] == "RenderTimeoutError"
    finally:
        settings.google_maps_api_key = original_google_key


@patch(
    f"{_SVC}._render_preview",
    new_callable=AsyncMock,
    side_effect=RenderError("crash"),
)
@patch(f"{_SVC}.save_manifest")
@patch(f"{_SVC}.ensure_preview_dir", return_value=Path("/tmp/test"))
@patch(f"{_SVC}.save_request")
@patch(f"{_SVC}.cleanup_expired")
@patch(
    f"{_SVC}.generate_preview_id",
    return_value="preview_test123",
)
def test_render_error_returns_502(_gen, _clean, _save, _dir, _mock_save_manifest, _render):
    from smallworld_api.config import settings

    original_google_key = settings.google_maps_api_key
    settings.google_maps_api_key = ""
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 502
    finally:
        settings.google_maps_api_key = original_google_key


def test_render_backend_not_configured():
    from smallworld_api.config import settings

    original = settings.preview_renderer_base_url
    settings.preview_renderer_base_url = ""
    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 503
    finally:
        settings.preview_renderer_base_url = original
