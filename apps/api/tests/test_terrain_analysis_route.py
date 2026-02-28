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
    tile_coords=[(12, 852, 1552)],
    zoom=12,
    cell_size_meters=78.0,
)


def _mock_snapshot():
    return patch(
        "smallworld_api.routes.terrain.fetch_dem_snapshot",
        new_callable=AsyncMock,
        return_value=_FAKE_SNAPSHOT,
    )


def test_analyze_returns_200():
    with _mock_snapshot():
        resp = client.post(
            "/api/v1/terrain/analyze",
            json={
                "center": {"lat": 39.75, "lng": -104.95},
                "radiusMeters": 5000,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "features" in data
    assert "hotspots" in data
    assert "scenes" in data
    assert data["source"] == "aws-terrarium"


def test_analyze_uses_default_weights():
    with _mock_snapshot():
        resp = client.post(
            "/api/v1/terrain/analyze",
            json={
                "center": {"lat": 39.75, "lng": -104.95},
                "radiusMeters": 5000,
            },
        )
    data = resp.json()
    w = data["request"]["weights"]
    assert w["peaks"] == 1.0
    assert w["ridges"] == 0.9
    assert w["relief"] == 1.0


def test_analyze_custom_weights():
    with _mock_snapshot():
        resp = client.post(
            "/api/v1/terrain/analyze",
            json={
                "center": {"lat": 39.75, "lng": -104.95},
                "radiusMeters": 5000,
                "weights": {"peaks": 2.0, "ridges": 0.0, "cliffs": 0.0, "water": 0.0, "relief": 0.5},
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["request"]["weights"]["peaks"] == 2.0


def test_analyze_all_zero_weights_returns_422():
    resp = client.post(
        "/api/v1/terrain/analyze",
        json={
            "center": {"lat": 39.75, "lng": -104.95},
            "radiusMeters": 5000,
            "weights": {"peaks": 0, "ridges": 0, "cliffs": 0, "water": 0, "relief": 0},
        },
    )
    assert resp.status_code == 422


def test_analyze_empty_features_returns_200():
    """Flat terrain with no prominent features should still return 200."""
    flat_snap = DEMSnapshot(
        dem=np.full((128, 128), 500.0),
        bounds=GeoBounds(north=39.8, south=39.7, east=-104.9, west=-105.0),
        tile_coords=[(12, 852, 1552)],
        zoom=12,
        cell_size_meters=78.0,
    )
    with patch(
        "smallworld_api.routes.terrain.fetch_dem_snapshot",
        new_callable=AsyncMock,
        return_value=flat_snap,
    ):
        resp = client.post(
            "/api/v1/terrain/analyze",
            json={
                "center": {"lat": 39.75, "lng": -104.95},
                "radiusMeters": 5000,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["features"]["peaks"] == []
    assert data["hotspots"] == []
    assert data["scenes"] == []


def test_elevation_grid_still_works():
    """Hour-one endpoint must remain intact."""
    with patch(
        "smallworld_api.routes.terrain.get_elevation_grid",
        new_callable=AsyncMock,
        return_value={
            "request": {"center": {"lat": 39.75, "lng": -104.95}, "radiusMeters": 5000, "zoomUsed": 12},
            "bounds": {"north": 39.8, "south": 39.7, "east": -104.9, "west": -105.0},
            "grid": {"width": 128, "height": 128, "cellSizeMetersApprox": 78.0, "elevations": [[0.0]]},
            "tiles": [{"z": 12, "x": 852, "y": 1552}],
            "stats": {"minElevation": 500.0, "maxElevation": 1500.0, "meanElevation": 900.0},
            "source": "aws-terrarium",
        },
    ):
        resp = client.post(
            "/api/v1/terrain/elevation-grid",
            json={
                "center": {"lat": 39.75, "lng": -104.95},
                "radiusMeters": 5000,
            },
        )
    assert resp.status_code == 200
    assert "stats" in resp.json()
