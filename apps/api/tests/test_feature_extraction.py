import numpy as np

from smallworld_api.services.derivatives import (
    compute_profile_curvature,
    compute_slope_degrees,
)
from smallworld_api.services.features import (
    extract_cliffs,
    extract_peaks,
    extract_ridges,
    extract_water_channels,
)
from smallworld_api.services.tiles import GeoBounds

BOUNDS = GeoBounds(north=40.0, south=39.5, east=-104.5, west=-105.0)
CELL_SIZE = 78.0


def _make_summit_dem() -> np.ndarray:
    """Create a DEM with a single prominent summit in the center."""
    dem = np.full((128, 128), 1000.0)
    # Build a cone peaking at center
    for r in range(128):
        for c in range(128):
            dist = np.sqrt((r - 64) ** 2 + (c - 64) ** 2)
            dem[r, c] = max(1000.0, 2000.0 - dist * 12.0)
    return dem


def _make_valley_dem() -> np.ndarray:
    """Create a DEM with a valley running north-south through the center."""
    dem = np.zeros((128, 128))
    for r in range(128):
        for c in range(128):
            dem[r, c] = 1000.0 + abs(c - 64) * 10.0
    return dem


def _make_step_dem() -> np.ndarray:
    """Create a DEM with a sharp vertical step — cliff-like."""
    dem = np.full((128, 128), 1000.0)
    dem[:, 64:] = 1500.0
    return dem


def test_single_summit_produces_peak():
    dem = _make_summit_dem()
    peaks = extract_peaks(dem, BOUNDS, min_prominence=50)
    assert len(peaks) >= 1
    top = peaks[0]
    assert top["elevationMeters"] > 1500
    assert top["prominenceMetersApprox"] > 50


def test_valley_produces_water_channel():
    dem = _make_valley_dem()
    channels = extract_water_channels(dem, BOUNDS, CELL_SIZE, threshold=10)
    assert len(channels) >= 1
    assert channels[0]["lengthMetersApprox"] > 0


def test_inverted_valley_produces_ridge():
    dem = _make_valley_dem()
    inverted_dem = dem.max() - dem + 1000  # Invert so valley becomes ridge
    ridges = extract_ridges(inverted_dem, BOUNDS, CELL_SIZE, threshold=10)
    assert len(ridges) >= 1
    assert ridges[0]["lengthMetersApprox"] > 0


def test_step_produces_cliff():
    dem = _make_step_dem()
    slope = compute_slope_degrees(dem, CELL_SIZE)
    curv = compute_profile_curvature(dem, CELL_SIZE)
    cliffs = extract_cliffs(slope, curv, BOUNDS, dem, min_slope=5)
    assert len(cliffs) >= 1
    assert cliffs[0]["dropMetersApprox"] > 0
