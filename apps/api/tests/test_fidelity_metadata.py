"""Tests for additive fidelity metadata in terrain route responses.

Validates that the /elevation-grid, /analyze, and /viewpoints endpoints
all include a fidelity field with the correct structure, and that the
addition is backward-compatible.
"""

from unittest.mock import AsyncMock, patch

import numpy as np
from fastapi.testclient import TestClient

from smallworld_api.main import app
from smallworld_api.services.terrarium import DEMSnapshot
from smallworld_api.services.tiles import GeoBounds

client = TestClient(app)

_FAKE_SNAPSHOT = DEMSnapshot(
    dem=np.random.rand(128, 128) * 1000 + 500,
    bounds=GeoBounds(north=39.8, south=39.7, east=-104.9, west=-105.0),
    tile_coords=[(12, 852, 1552), (12, 853, 1552)],
    zoom=12,
    cell_size_meters=78.0,
    zoom_requested=13,
)

_VALID_CENTER = {"lat": 39.75, "lng": -104.95}
_VALID_RADIUS = 5000

_FIDELITY_KEYS = {
    "demProvider",
    "zoomRequested",
    "zoomUsed",
    "gridWidth",
    "gridHeight",
    "resampleMethod",
    "tileCount",
}


def _mock_snapshot():
    return patch(
        "smallworld_api.routes.terrain.fetch_dem_snapshot",
        new_callable=AsyncMock,
        return_value=_FAKE_SNAPSHOT,
    )


def _mock_generate_viewpoints():
    return patch(
        "smallworld_api.routes.terrain.generate_viewpoints",
        return_value={
            "viewpoints": [],
            "summary": {
                "sceneCount": 0,
                "eligibleSceneCount": 0,
                "candidatesGenerated": 0,
                "candidatesRejected": {
                    "templateIneligible": 0,
                    "noConvergence": 0,
                    "underground": 0,
                    "occluded": 0,
                    "outOfBounds": 0,
                },
                "returned": 0,
            },
        },
    )


# ── /elevation-grid fidelity ──────────────────────────────────────────────


def _mock_elevation_grid_result():
    """Build a mock result dict that includes fidelity metadata."""
    grid = np.random.uniform(1500, 2500, (128, 128))
    return {
        "request": {
            "center": _VALID_CENTER,
            "radiusMeters": _VALID_RADIUS,
            "zoomUsed": 12,
        },
        "bounds": {"north": 39.8, "south": 39.7, "east": -104.9, "west": -105.0},
        "grid": {
            "width": 128,
            "height": 128,
            "cellSizeMetersApprox": 78.0,
            "elevations": np.round(grid, 1).tolist(),
        },
        "tiles": [{"z": 12, "x": 852, "y": 1552}],
        "stats": {
            "minElevation": round(float(np.min(grid)), 1),
            "maxElevation": round(float(np.max(grid)), 1),
            "meanElevation": round(float(np.mean(grid)), 1),
        },
        "source": "aws-terrarium",
        "fidelity": {
            "demProvider": "terrarium",
            "zoomRequested": 13,
            "zoomUsed": 12,
            "gridWidth": 128,
            "gridHeight": 128,
            "resampleMethod": "bilinear",
            "tileCount": 1,
        },
    }


@patch("smallworld_api.routes.terrain.get_elevation_grid", new_callable=AsyncMock)
def test_elevation_grid_includes_fidelity(mock_get):
    """The /elevation-grid response should include a fidelity field."""
    mock_get.return_value = _mock_elevation_grid_result()
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "fidelity" in body
    assert set(body["fidelity"].keys()) == _FIDELITY_KEYS


@patch("smallworld_api.routes.terrain.get_elevation_grid", new_callable=AsyncMock)
def test_elevation_grid_fidelity_values(mock_get):
    """Fidelity values in /elevation-grid should match expected defaults."""
    mock_get.return_value = _mock_elevation_grid_result()
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
    )
    fidelity = resp.json()["fidelity"]
    assert fidelity["demProvider"] == "terrarium"
    assert fidelity["resampleMethod"] == "bilinear"
    assert fidelity["gridWidth"] == 128
    assert fidelity["gridHeight"] == 128


@patch("smallworld_api.routes.terrain.get_elevation_grid", new_callable=AsyncMock)
def test_elevation_grid_backward_compatible_without_fidelity(mock_get):
    """If fidelity is absent from the service response, the endpoint
    should still return 200 (fidelity is optional)."""
    result = _mock_elevation_grid_result()
    del result["fidelity"]
    mock_get.return_value = result
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
    )
    assert resp.status_code == 200
    body = resp.json()
    # fidelity should be None/null when not provided by the service
    assert body.get("fidelity") is None


# ── /analyze fidelity ─────────────────────────────────────────────────────


def test_analyze_includes_fidelity():
    """The /analyze response should include a fidelity field."""
    with _mock_snapshot():
        resp = client.post(
            "/api/v1/terrain/analyze",
            json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "fidelity" in body
    assert set(body["fidelity"].keys()) == _FIDELITY_KEYS


def test_analyze_fidelity_values():
    """Fidelity values in /analyze should reflect the snapshot."""
    with _mock_snapshot():
        resp = client.post(
            "/api/v1/terrain/analyze",
            json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
        )
    fidelity = resp.json()["fidelity"]
    assert fidelity["demProvider"] == "terrarium"
    assert fidelity["resampleMethod"] == "bilinear"
    assert fidelity["gridWidth"] == 128
    assert fidelity["gridHeight"] == 128
    assert fidelity["zoomUsed"] == 12
    assert fidelity["zoomRequested"] == 13
    assert fidelity["tileCount"] == 2  # _FAKE_SNAPSHOT has 2 tile_coords


# ── /viewpoints fidelity ─────────────────────────────────────────────────


def test_viewpoints_includes_fidelity():
    """The /viewpoints response should include a fidelity field."""
    with _mock_snapshot(), _mock_generate_viewpoints():
        resp = client.post(
            "/api/v1/terrain/viewpoints",
            json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "fidelity" in body
    assert set(body["fidelity"].keys()) == _FIDELITY_KEYS


def test_viewpoints_fidelity_values():
    """Fidelity values in /viewpoints should reflect the snapshot."""
    with _mock_snapshot(), _mock_generate_viewpoints():
        resp = client.post(
            "/api/v1/terrain/viewpoints",
            json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
        )
    fidelity = resp.json()["fidelity"]
    assert fidelity["demProvider"] == "terrarium"
    assert fidelity["resampleMethod"] == "bilinear"
    assert fidelity["gridWidth"] == 128
    assert fidelity["gridHeight"] == 128
    assert fidelity["zoomUsed"] == 12
    assert fidelity["zoomRequested"] == 13
    assert fidelity["tileCount"] == 2


# ── Cross-endpoint consistency ────────────────────────────────────────────


def test_analyze_and_viewpoints_fidelity_match():
    """When fed the same snapshot, /analyze and /viewpoints should produce
    identical fidelity metadata."""
    with _mock_snapshot():
        analyze_resp = client.post(
            "/api/v1/terrain/analyze",
            json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
        )

    with _mock_snapshot(), _mock_generate_viewpoints():
        viewpoints_resp = client.post(
            "/api/v1/terrain/viewpoints",
            json={"center": _VALID_CENTER, "radiusMeters": _VALID_RADIUS},
        )

    assert analyze_resp.json()["fidelity"] == viewpoints_resp.json()["fidelity"]
