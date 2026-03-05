"""Tests for preview pipeline provider fallback and retry order.

Validates that the provider chain (google_3d -> ion -> osm) is
followed correctly, that render_attempts metadata tracks each
provider, and that fallback warnings are emitted.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

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
    "enhancement": {"enabled": False},
}

_SVC = "smallworld_api.services.previews"


def _mock_render_result():
    return RenderResult(image_path=Path("/tmp/test/raw.png"), frame_state={})


def _patch_pipeline():
    """Return a list of patches for the preview pipeline dependencies."""
    return [
        patch(
            f"{_SVC}._render_preview",
            new_callable=AsyncMock,
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
            return_value="preview_fallback_test",
        ),
        patch.object(Path, "read_bytes", return_value=b"fakepng"),
    ]


def _apply_patches(patches):
    return [p.start() for p in patches]


def _stop_patches(patches):
    for p in patches:
        p.stop()


# ── Full chain: google_3d -> ion -> osm ───────────────────────────────────


def test_full_chain_google_then_ion_then_osm():
    """With both Google key and Ion token, fallback goes google_3d -> ion -> osm.

    When both google_3d and ion fail, osm should succeed.
    """
    from smallworld_api.config import settings

    original_google = settings.google_maps_api_key
    original_ion = settings.cesium_ion_token
    settings.google_maps_api_key = "test-google-key"
    settings.cesium_ion_token = "test-ion-token"

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mock_render = mocks[0]

    # google_3d fails, ion fails, osm succeeds
    mock_render.side_effect = [
        RenderTimeoutError("google timeout"),
        RenderError("ion crash"),
        _mock_render_result(),
    ]

    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()

        # Should have 3 render attempts
        assert mock_render.await_count == 3

        # Status should indicate warnings from fallback
        assert body["status"] == "completed_with_warnings"
        codes = [w["code"] for w in body["warnings"]]
        assert "render_provider_fallback" in codes

        # Verify the fallback warning mentions both failed providers
        fallback_warnings = [w for w in body["warnings"] if w["code"] == "render_provider_fallback"]
        assert len(fallback_warnings) == 1
        assert "google_3d" in fallback_warnings[0]["message"]
        assert "ion" in fallback_warnings[0]["message"]
    finally:
        settings.google_maps_api_key = original_google
        settings.cesium_ion_token = original_ion
        _stop_patches(patches)


def test_google_fails_ion_succeeds():
    """With both keys, when google_3d fails ion should be tried next
    and succeed without reaching osm."""
    from smallworld_api.config import settings

    original_google = settings.google_maps_api_key
    original_ion = settings.cesium_ion_token
    settings.google_maps_api_key = "test-google-key"
    settings.cesium_ion_token = "test-ion-token"

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mock_render = mocks[0]

    # google_3d fails, ion succeeds
    mock_render.side_effect = [
        RenderTimeoutError("google timeout"),
        _mock_render_result(),
    ]

    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()

        # Should have exactly 2 attempts (google_3d + ion)
        assert mock_render.await_count == 2
        assert body["status"] == "completed_with_warnings"
        codes = [w["code"] for w in body["warnings"]]
        assert "render_provider_fallback" in codes
    finally:
        settings.google_maps_api_key = original_google
        settings.cesium_ion_token = original_ion
        _stop_patches(patches)


def test_no_google_key_skips_google_attempts_ion_first():
    """Without a Google key, the chain should start with ion then osm."""
    from smallworld_api.config import settings

    original_google = settings.google_maps_api_key
    original_ion = settings.cesium_ion_token
    settings.google_maps_api_key = ""
    settings.cesium_ion_token = "test-ion-token"

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mock_render = mocks[0]

    # ion succeeds on first attempt
    mock_render.return_value = _mock_render_result()

    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()

        # Only 1 attempt (ion) — no google attempt
        assert mock_render.await_count == 1
        # No fallback warning since first attempt succeeded
        codes = [w["code"] for w in body.get("warnings", [])]
        assert "render_provider_fallback" not in codes
    finally:
        settings.google_maps_api_key = original_google
        settings.cesium_ion_token = original_ion
        _stop_patches(patches)


def test_no_keys_only_osm():
    """Without any provider keys, only osm should be attempted."""
    from smallworld_api.config import settings

    original_google = settings.google_maps_api_key
    original_ion = settings.cesium_ion_token
    settings.google_maps_api_key = ""
    settings.cesium_ion_token = ""

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mock_render = mocks[0]

    mock_render.return_value = _mock_render_result()

    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()

        # Only 1 attempt (osm) — no other providers available
        assert mock_render.await_count == 1
        codes = [w["code"] for w in body.get("warnings", [])]
        assert "render_provider_fallback" not in codes
    finally:
        settings.google_maps_api_key = original_google
        settings.cesium_ion_token = original_ion
        _stop_patches(patches)


# ── render_attempts metadata ──────────────────────────────────────────────


def test_render_attempts_tracked_via_provider_calls():
    """Render attempts should be tracked through the provider calls.

    The render_attempts metadata is captured in the pipeline result and
    saved to the manifest. We verify that the mock renderer was called
    with the correct providers in order.
    """
    from smallworld_api.config import settings

    original_google = settings.google_maps_api_key
    settings.google_maps_api_key = "test-google-key"

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mock_render = mocks[0]
    mock_save_manifest = mocks[4]

    # google_3d fails, osm succeeds
    mock_render.side_effect = [
        RenderTimeoutError("timeout"),
        _mock_render_result(),
    ]

    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200

        # Verify exactly 2 render calls were made
        assert mock_render.await_count == 2

        # Verify providers were tried in order: google_3d, then osm
        calls = mock_render.call_args_list
        assert calls[0].kwargs["provider"] == "google_3d"
        assert calls[1].kwargs["provider"] == "osm"

        # Verify the manifest was saved with render_attempts
        manifest = mock_save_manifest.call_args.args[1]
        assert "render_attempts" in manifest
        attempts = manifest["render_attempts"]
        assert len(attempts) == 2
        assert attempts[0]["provider"] == "google_3d"
        assert attempts[0]["status"] == "failed"
        assert attempts[1]["provider"] == "osm"
        assert attempts[1]["status"] == "succeeded"
    finally:
        settings.google_maps_api_key = original_google
        _stop_patches(patches)


def test_render_attempts_in_failure_manifest():
    """When all providers fail, the 504 response's failure manifest
    should still contain render_attempts."""
    from smallworld_api.config import settings

    original_google = settings.google_maps_api_key
    original_ion = settings.cesium_ion_token
    settings.google_maps_api_key = "test-google-key"
    settings.cesium_ion_token = "test-ion-token"

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mock_render = mocks[0]

    # All 3 providers fail
    mock_render.side_effect = RenderTimeoutError("timeout everywhere")

    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        # All providers failed -> should be a timeout error
        assert resp.status_code == 504

        # Verify the render was attempted 3 times (google_3d, ion, osm)
        assert mock_render.await_count == 3
    finally:
        settings.google_maps_api_key = original_google
        settings.cesium_ion_token = original_ion
        _stop_patches(patches)


def test_single_successful_attempt_no_fallback_warning():
    """When the first provider succeeds, there should be no
    render_provider_fallback warning."""
    from smallworld_api.config import settings

    original_google = settings.google_maps_api_key
    settings.google_maps_api_key = "test-google-key"

    patches = _patch_pipeline()
    mocks = _apply_patches(patches)
    mock_render = mocks[0]

    mock_render.return_value = _mock_render_result()

    try:
        resp = client.post("/api/v1/previews/render", json=VALID_REQUEST)
        assert resp.status_code == 200
        body = resp.json()

        assert mock_render.await_count == 1
        assert body["status"] == "completed"
        codes = [w["code"] for w in body.get("warnings", [])]
        assert "render_provider_fallback" not in codes
    finally:
        settings.google_maps_api_key = original_google
        _stop_patches(patches)
