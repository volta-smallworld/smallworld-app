from unittest.mock import AsyncMock, patch

import httpx
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

_VIEWPOINTS_URL = "/api/v1/terrain/viewpoints"

_VALID_BODY = {
    "center": {"lat": 39.75, "lng": -104.95},
    "radiusMeters": 5000,
}

_MOCK_GENERATE_RESULT = {
    "viewpoints": [
        {
            "id": "vp-1",
            "sceneId": "scene-1",
            "sceneType": "peak-ridge",
            "composition": "ruleOfThirds",
            "camera": {
                "lat": 46.5,
                "lng": 7.5,
                "altitudeMeters": 2500.0,
                "headingDegrees": 180.0,
                "pitchDegrees": -5.0,
                "rollDegrees": 0,
                "fovDegrees": 55,
            },
            "targets": [
                {"featureId": "peak-1", "role": "primary", "xNorm": 0.667, "yNorm": 0.333},
                {"featureId": "ridge-1", "role": "secondary", "xNorm": 0.333, "yNorm": 0.667},
            ],
            "distanceMetersApprox": 1200.0,
            "validation": {"clearanceMeters": 50.0, "visibleTargetIds": ["peak-1", "ridge-1"]},
            "score": 0.75,
            "scoreBreakdown": {
                "viewshedRichness": 0.8,
                "terrainEntropy": 0.7,
                "skylineFractal": 0.9,
                "prospectRefuge": 0.6,
                "depthLayering": 0.5,
                "mystery": 0.7,
                "waterVisibility": 0.3,
            },
        }
    ],
    "summary": {
        "sceneCount": 3,
        "eligibleSceneCount": 2,
        "candidatesGenerated": 8,
        "candidatesRejected": {
            "templateIneligible": 1,
            "noConvergence": 2,
            "underground": 0,
            "occluded": 1,
            "outOfBounds": 0,
        },
        "returned": 1,
    },
}


def _mock_snapshot():
    return patch(
        "smallworld_api.routes.terrain.fetch_dem_snapshot",
        new_callable=AsyncMock,
        return_value=_FAKE_SNAPSHOT,
    )


def _mock_generate():
    return patch(
        "smallworld_api.routes.terrain.generate_viewpoints",
        return_value=_MOCK_GENERATE_RESULT,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_viewpoints_returns_200():
    with _mock_snapshot(), _mock_generate():
        resp = client.post(_VIEWPOINTS_URL, json=_VALID_BODY)
    assert resp.status_code == 200
    data = resp.json()
    assert "viewpoints" in data
    assert "summary" in data
    assert "request" in data
    assert data["source"] == "aws-terrarium"


def test_viewpoints_response_structure():
    with _mock_snapshot(), _mock_generate():
        resp = client.post(_VIEWPOINTS_URL, json=_VALID_BODY)
    data = resp.json()

    # Request echo
    req = data["request"]
    assert req["center"]["lat"] == 39.75
    assert req["center"]["lng"] == -104.95
    assert req["radiusMeters"] == 5000
    assert req["zoomUsed"] == 12
    assert "weights" in req
    assert "compositions" in req
    assert "maxViewpoints" in req
    assert "maxPerScene" in req

    # Summary
    summary = data["summary"]
    assert summary["sceneCount"] == 3
    assert summary["eligibleSceneCount"] == 2
    assert summary["candidatesGenerated"] == 8
    assert summary["returned"] == 1
    assert summary["candidatesRejected"]["noConvergence"] == 2

    # Viewpoints
    vps = data["viewpoints"]
    assert len(vps) == 1
    vp = vps[0]
    assert vp["id"] == "vp-1"
    assert vp["sceneId"] == "scene-1"
    assert vp["sceneType"] == "peak-ridge"
    assert vp["composition"] == "ruleOfThirds"
    assert vp["score"] == 0.75
    assert vp["distanceMetersApprox"] == 1200.0

    # Camera
    cam = vp["camera"]
    assert cam["lat"] == 46.5
    assert cam["altitudeMeters"] == 2500.0
    assert cam["headingDegrees"] == 180.0
    assert cam["pitchDegrees"] == -5.0

    # Targets
    targets = vp["targets"]
    assert len(targets) == 2
    assert targets[0]["featureId"] == "peak-1"
    assert targets[0]["role"] == "primary"

    # Validation
    val = vp["validation"]
    assert val["clearanceMeters"] == 50.0
    assert val["visibleTargetIds"] == ["peak-1", "ridge-1"]

    # Score breakdown
    sb = vp["scoreBreakdown"]
    assert sb["viewshedRichness"] == 0.8
    assert sb["waterVisibility"] == 0.3


def test_viewpoints_default_compositions():
    with _mock_snapshot(), _mock_generate():
        resp = client.post(_VIEWPOINTS_URL, json=_VALID_BODY)
    data = resp.json()
    comps = data["request"]["compositions"]
    assert set(comps) == {"ruleOfThirds", "goldenRatio", "leadingLine", "symmetry"}


def test_viewpoints_custom_compositions():
    body = {**_VALID_BODY, "compositions": ["ruleOfThirds", "symmetry"]}
    with _mock_snapshot(), _mock_generate():
        resp = client.post(_VIEWPOINTS_URL, json=body)
    data = resp.json()
    assert data["request"]["compositions"] == ["ruleOfThirds", "symmetry"]


def test_viewpoints_custom_limits():
    body = {**_VALID_BODY, "maxViewpoints": 5, "maxPerScene": 2}
    with _mock_snapshot(), _mock_generate():
        resp = client.post(_VIEWPOINTS_URL, json=body)
    data = resp.json()
    assert data["request"]["maxViewpoints"] == 5
    assert data["request"]["maxPerScene"] == 2


def test_viewpoints_default_weights():
    with _mock_snapshot(), _mock_generate():
        resp = client.post(_VIEWPOINTS_URL, json=_VALID_BODY)
    data = resp.json()
    w = data["request"]["weights"]
    assert w["peaks"] == 1.0
    assert w["ridges"] == 0.9
    assert w["cliffs"] == 0.8
    assert w["water"] == 0.7
    assert w["relief"] == 1.0


def test_viewpoints_custom_weights():
    body = {
        **_VALID_BODY,
        "weights": {"peaks": 2.0, "ridges": 0.5, "cliffs": 0.0, "water": 0.0, "relief": 0.5},
    }
    with _mock_snapshot(), _mock_generate():
        resp = client.post(_VIEWPOINTS_URL, json=body)
    data = resp.json()
    assert data["request"]["weights"]["peaks"] == 2.0
    assert data["request"]["weights"]["ridges"] == 0.5


# ---------------------------------------------------------------------------
# Validation errors (422)
# ---------------------------------------------------------------------------


def test_viewpoints_invalid_center_lat_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={"center": {"lat": 91.0, "lng": -104.95}, "radiusMeters": 5000},
    )
    assert resp.status_code == 422


def test_viewpoints_invalid_center_lng_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={"center": {"lat": 39.75, "lng": 181.0}, "radiusMeters": 5000},
    )
    assert resp.status_code == 422


def test_viewpoints_missing_center_returns_422():
    resp = client.post(_VIEWPOINTS_URL, json={"radiusMeters": 5000})
    assert resp.status_code == 422


def test_viewpoints_radius_too_small_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={"center": {"lat": 39.75, "lng": -104.95}, "radiusMeters": 500},
    )
    assert resp.status_code == 422


def test_viewpoints_radius_too_large_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={"center": {"lat": 39.75, "lng": -104.95}, "radiusMeters": 60000},
    )
    assert resp.status_code == 422


def test_viewpoints_all_zero_weights_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={
            **_VALID_BODY,
            "weights": {"peaks": 0, "ridges": 0, "cliffs": 0, "water": 0, "relief": 0},
        },
    )
    assert resp.status_code == 422


def test_viewpoints_invalid_composition_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={**_VALID_BODY, "compositions": ["invalidComposition"]},
    )
    assert resp.status_code == 422


def test_viewpoints_maxViewpoints_too_large_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={**_VALID_BODY, "maxViewpoints": 30},
    )
    assert resp.status_code == 422


def test_viewpoints_maxPerScene_too_large_returns_422():
    resp = client.post(
        _VIEWPOINTS_URL,
        json={**_VALID_BODY, "maxPerScene": 10},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Upstream tile error (502)
# ---------------------------------------------------------------------------


def test_viewpoints_upstream_http_error_returns_502():
    mock_response = httpx.Response(status_code=503, request=httpx.Request("GET", "https://tile.example.com"))
    with patch(
        "smallworld_api.routes.terrain.fetch_dem_snapshot",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Service Unavailable", request=mock_response.request, response=mock_response
        ),
    ):
        resp = client.post(_VIEWPOINTS_URL, json=_VALID_BODY)
    assert resp.status_code == 502
    assert "Upstream tile fetch failed" in resp.json()["detail"]


def test_viewpoints_upstream_request_error_returns_502():
    with patch(
        "smallworld_api.routes.terrain.fetch_dem_snapshot",
        new_callable=AsyncMock,
        side_effect=httpx.RequestError("Connection refused", request=httpx.Request("GET", "https://tile.example.com")),
    ):
        resp = client.post(_VIEWPOINTS_URL, json=_VALID_BODY)
    assert resp.status_code == 502
    assert "Upstream tile fetch failed" in resp.json()["detail"]


def test_viewpoints_value_error_returns_422():
    with patch(
        "smallworld_api.routes.terrain.fetch_dem_snapshot",
        new_callable=AsyncMock,
        side_effect=ValueError("Too many tiles requested"),
    ):
        resp = client.post(_VIEWPOINTS_URL, json=_VALID_BODY)
    assert resp.status_code == 422
    assert "Too many tiles" in resp.json()["detail"]
