"""Tests for GET /api/v1/previews/capabilities endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from smallworld_api.config import settings
from smallworld_api.main import app

client = TestClient(app)


def _with_settings(**overrides):
    """Context manager-like helper to temporarily override settings."""
    originals = {}
    for key, val in overrides.items():
        originals[key] = getattr(settings, key)
        setattr(settings, key, val)
    return originals


def _restore_settings(originals):
    for key, val in originals.items():
        setattr(settings, key, val)


def test_capabilities_all_keys():
    orig = _with_settings(
        google_maps_api_key="test-google",
        cesium_ion_token="test-ion",
        preview_renderer_base_url="http://localhost:4182/render/preview",
    )
    try:
        resp = client.get("/api/v1/previews/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["rendererConfigured"] is True
        assert body["availableProviders"] == ["google_3d", "ion", "osm"]
        assert body["activeProvider"] == "google_3d"
        assert body["providerOrder"] == ["google_3d", "ion", "osm"]
        assert body["eagerCount"] == settings.preview_eager_count
        assert body["message"] is None
    finally:
        _restore_settings(orig)


def test_capabilities_google_only():
    orig = _with_settings(
        google_maps_api_key="test-google",
        cesium_ion_token="",
        preview_renderer_base_url="http://localhost:4182/render/preview",
    )
    try:
        resp = client.get("/api/v1/previews/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["availableProviders"] == ["google_3d", "osm"]
        assert body["activeProvider"] == "google_3d"
    finally:
        _restore_settings(orig)


def test_capabilities_ion_only():
    orig = _with_settings(
        google_maps_api_key="",
        cesium_ion_token="test-ion",
        preview_renderer_base_url="http://localhost:4182/render/preview",
    )
    try:
        resp = client.get("/api/v1/previews/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["availableProviders"] == ["ion", "osm"]
        assert body["activeProvider"] == "ion"
    finally:
        _restore_settings(orig)


def test_capabilities_no_keys():
    orig = _with_settings(
        google_maps_api_key="",
        cesium_ion_token="",
        preview_renderer_base_url="http://localhost:4182/render/preview",
    )
    try:
        resp = client.get("/api/v1/previews/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["availableProviders"] == ["osm"]
        assert body["activeProvider"] == "osm"
    finally:
        _restore_settings(orig)


def test_capabilities_no_renderer():
    orig = _with_settings(
        google_maps_api_key="test-google",
        cesium_ion_token="test-ion",
        preview_renderer_base_url="",
    )
    try:
        resp = client.get("/api/v1/previews/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["rendererConfigured"] is False
        assert body["message"] is not None
        assert "not configured" in body["message"].lower()
    finally:
        _restore_settings(orig)


def test_capabilities_eager_count_from_settings():
    orig = _with_settings(
        google_maps_api_key="",
        cesium_ion_token="",
        preview_renderer_base_url="http://localhost:4182/render/preview",
        preview_eager_count=7,
    )
    try:
        resp = client.get("/api/v1/previews/capabilities")
        assert resp.status_code == 200
        body = resp.json()
        assert body["eagerCount"] == 7
    finally:
        _restore_settings(orig)
