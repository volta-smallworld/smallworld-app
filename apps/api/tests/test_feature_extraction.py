import numpy as np

from smallworld_api.services.derivatives import (
    compute_profile_curvature,
    compute_slope_degrees,
)
from smallworld_api.services.features import (
    _mask_to_paths,
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


def test_diagonal_mask_traces_single_path():
    mask = np.zeros((16, 16), dtype=bool)
    for idx in range(6):
        mask[idx + 2, idx + 2] = True

    paths = _mask_to_paths(mask, BOUNDS, np.zeros((16, 16)), CELL_SIZE, min_cells=1)

    assert len(paths) == 1
    assert len(paths[0]["path"]) == 6
    assert paths[0]["lengthMetersApprox"] > 0


def test_mask_path_order_stays_connected_through_branches():
    mask = np.zeros((16, 16), dtype=bool)
    trunk = [(2, 2), (3, 2), (4, 2), (5, 2), (6, 2)]
    branch = [(4, 3), (4, 4), (4, 5), (4, 6)]
    for r, c in trunk + branch:
        mask[r, c] = True

    paths = _mask_to_paths(mask, BOUNDS, np.zeros((16, 16)), CELL_SIZE, min_cells=1)
    assert len(paths) == 1
    assert len(paths[0]["path"]) >= 2

    def _to_grid(pt: dict) -> tuple[int, int]:
        row = int(round((BOUNDS.north - pt["lat"]) / (BOUNDS.north - BOUNDS.south) * 15))
        col = int(round((pt["lng"] - BOUNDS.west) / (BOUNDS.east - BOUNDS.west) * 15))
        return row, col

    grid_points = [_to_grid(pt) for pt in paths[0]["path"]]
    for (r1, c1), (r2, c2) in zip(grid_points, grid_points[1:]):
        assert max(abs(r2 - r1), abs(c2 - c1)) <= 1


def test_flat_topped_summit_collapses_to_single_peak():
    dem = np.full((128, 128), 1000.0)
    dem[50:60, 50:60] = 2000.0

    peaks = extract_peaks(dem, BOUNDS, min_prominence=50)

    assert len(peaks) == 1
    assert peaks[0]["elevationMeters"] == 2000.0
