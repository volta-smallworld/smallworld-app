from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smallworld_api.main import app

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
