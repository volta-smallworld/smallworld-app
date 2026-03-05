from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smallworld_api.main import app
from smallworld_api.services.point_context import PointContextResult

client = TestClient(app)


def _mock_grid_result():
    grid = np.random.uniform(1500, 2500, (128, 128))
    return {
        "request": {
            "center": {"lat": 39.7392, "lng": -104.9903},
            "radiusMeters": 5000,
            "zoomUsed": 12,
        },
        "bounds": {
            "north": 39.7841,
            "south": 39.6943,
            "east": -104.9321,
            "west": -105.0485,
        },
        "grid": {
            "width": 128,
            "height": 128,
            "cellSizeMetersApprox": 78.1,
            "elevations": np.round(grid, 1).tolist(),
        },
        "tiles": [{"z": 12, "x": 852, "y": 1552}],
        "stats": {
            "minElevation": round(float(np.min(grid)), 1),
            "maxElevation": round(float(np.max(grid)), 1),
            "meanElevation": round(float(np.mean(grid)), 1),
        },
        "source": "aws-terrarium",
    }


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch("smallworld_api.routes.terrain.get_elevation_grid", new_callable=AsyncMock)
def test_valid_request(mock_get):
    mock_get.return_value = _mock_grid_result()
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={
            "center": {"lat": 39.7392, "lng": -104.9903},
            "radiusMeters": 5000,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "bounds" in body
    assert "grid" in body
    assert "tiles" in body
    assert "stats" in body
    assert body["grid"]["width"] == 128
    assert body["grid"]["height"] == 128
    assert body["source"] == "aws-terrarium"


def test_invalid_radius_too_small():
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={
            "center": {"lat": 39.7392, "lng": -104.9903},
            "radiusMeters": 500,
        },
    )
    assert resp.status_code == 422


def test_invalid_radius_too_large():
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={
            "center": {"lat": 39.7392, "lng": -104.9903},
            "radiusMeters": 100000,
        },
    )
    assert resp.status_code == 422


def test_invalid_lat():
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={
            "center": {"lat": 95.0, "lng": -104.9903},
            "radiusMeters": 5000,
        },
    )
    assert resp.status_code == 422


@patch("smallworld_api.routes.terrain.get_elevation_grid", new_callable=AsyncMock)
def test_oversized_tile_request(mock_get):
    mock_get.side_effect = ValueError("Request covers 100 tiles, exceeding the maximum of 36.")
    resp = client.post(
        "/api/v1/terrain/elevation-grid",
        json={
            "center": {"lat": 39.7392, "lng": -104.9903},
            "radiusMeters": 50000,
        },
    )
    assert resp.status_code == 422


# ── Point context endpoint ───────────────────────────────────────────────


def _mock_point_context_result():
    return PointContextResult(
        ground_elevation_meters=1500.0,
        camera_agl_meters=100.0,
        sampling={
            "zoom": 14,
            "tiles_fetched": 1,
            "meters_per_pixel_approx": 9.5,
            "method": "bilinear_raw_tile",
        },
        context={
            "radius_meters": 2000,
            "cell_size_meters": 15.6,
            "elevation": {"min": 1400.0, "max": 1600.0, "mean": 1500.0},
            "slope_degrees": {"at_point": 5.2, "min": 0.1, "max": 35.0, "mean": 12.5},
            "curvature": {"at_point": 0.001, "min": -0.01, "max": 0.02, "mean": 0.001},
            "local_relief_meters": {"at_point": 50.0, "min": 10.0, "max": 200.0, "mean": 75.0},
        },
    )


@patch("smallworld_api.routes.terrain.get_point_context", new_callable=AsyncMock)
def test_point_context_valid(mock_get):
    mock_get.return_value = _mock_point_context_result()
    resp = client.post(
        "/api/v1/terrain/point-context",
        json={
            "point": {"lat": 39.7392, "lng": -104.9903},
            "cameraAltitudeMeters": 1600.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["groundElevationMeters"] == 1500.0
    assert body["cameraAglMeters"] == 100.0
    assert body["sampling"]["method"] == "bilinear_raw_tile"
    assert body["context"] is not None
    assert body["context"]["slopeDegrees"]["atPoint"] == 5.2


def test_point_context_invalid_lat():
    resp = client.post(
        "/api/v1/terrain/point-context",
        json={
            "point": {"lat": 95.0, "lng": -104.9903},
        },
    )
    assert resp.status_code == 422


def test_point_context_invalid_context_radius():
    resp = client.post(
        "/api/v1/terrain/point-context",
        json={
            "point": {"lat": 39.7, "lng": -105.0},
            "contextRadiusMeters": 100,
        },
    )
    assert resp.status_code == 422


@patch("smallworld_api.routes.terrain.get_point_context", new_callable=AsyncMock)
def test_point_context_upstream_error(mock_get):
    import httpx

    mock_get.side_effect = httpx.RequestError("Connection failed")
    resp = client.post(
        "/api/v1/terrain/point-context",
        json={
            "point": {"lat": 39.7, "lng": -105.0},
        },
    )
    assert resp.status_code == 502
