import numpy as np

from smallworld_api.services.analysis import (
    build_interest_raster,
    build_layer_contributions,
    extract_hotspots,
)
from smallworld_api.services.tiles import GeoBounds

BOUNDS = GeoBounds(north=1.0, south=0.0, east=1.0, west=0.0)


def test_flat_hotspot_region_returns_single_hotspot():
    dem = np.zeros((128, 128))
    relief = np.zeros((128, 128))
    ridge = {
        "id": "ridge-1",
        "path": [{"lat": 0.5, "lng": x / 127} for x in range(20, 108)],
        "score": 1.0,
        "lengthMetersApprox": 1000,
    }
    weights = {"peaks": 0.0, "ridges": 1.0, "cliffs": 0.0, "water": 0.0, "relief": 0.0}

    interest = build_interest_raster(
        dem, relief, np.zeros((128, 128)), [], [ridge], [], [], BOUNDS, weights
    )
    layer_contributions = build_layer_contributions(
        dem, relief, np.zeros((128, 128)), [], [ridge], [], [], BOUNDS
    )
    hotspots = extract_hotspots(interest, BOUNDS, weights, layer_contributions)

    assert len(hotspots) == 1
    assert hotspots[0]["reasons"] == ["ridges"]


def test_hotspot_reasons_ignore_zero_weight_layers():
    dem = np.zeros((128, 128))
    relief = np.zeros((128, 128))
    relief[64, 64] = 10.0
    peak = {
        "id": "peak-1",
        "center": {"lat": 0.5, "lng": 0.5},
        "score": 1.0,
        "elevationMeters": 1000.0,
        "prominenceMetersApprox": 100.0,
    }
    weights = {"peaks": 0.0, "ridges": 0.0, "cliffs": 0.0, "water": 0.0, "relief": 1.0}

    interest = build_interest_raster(
        dem, relief, np.zeros((128, 128)), [peak], [], [], [], BOUNDS, weights
    )
    layer_contributions = build_layer_contributions(
        dem, relief, np.zeros((128, 128)), [peak], [], [], [], BOUNDS
    )
    hotspots = extract_hotspots(interest, BOUNDS, weights, layer_contributions)

    assert len(hotspots) == 1
    assert hotspots[0]["reasons"] == ["relief"]
