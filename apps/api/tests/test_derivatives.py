import numpy as np

from smallworld_api.services.derivatives import (
    compute_local_relief,
    compute_profile_curvature,
    compute_slope_degrees,
)


def test_flat_plane_slope_near_zero():
    dem = np.full((128, 128), 500.0)
    slope = compute_slope_degrees(dem, cell_size=78.0)
    assert slope.shape == (128, 128)
    assert np.allclose(slope, 0.0, atol=1e-6)


def test_flat_plane_curvature_near_zero():
    dem = np.full((128, 128), 500.0)
    curv = compute_profile_curvature(dem, cell_size=78.0)
    assert curv.shape == (128, 128)
    assert np.allclose(curv, 0.0, atol=1e-6)


def test_linear_ramp_has_stable_nonzero_slope():
    """A linear ramp tilting north-to-south should have consistent slope."""
    dem = np.zeros((128, 128))
    for r in range(128):
        dem[r, :] = 1000.0 - r * 5.0  # 5m drop per row
    slope = compute_slope_degrees(dem, cell_size=78.0)
    # Interior cells should all have similar slope
    interior = slope[10:-10, 10:-10]
    assert interior.min() > 0.5
    assert np.std(interior) < 1.0  # stable


def test_plateau_local_relief_elevated_at_edge():
    """A plateau surrounded by lowland should have elevated relief at the edge."""
    dem = np.full((128, 128), 100.0)
    dem[40:90, 40:90] = 800.0  # plateau in the middle
    relief = compute_local_relief(dem, window=21)
    assert relief.shape == (128, 128)
    # Edge of plateau should have high relief
    edge_relief = relief[40, 50]
    center_relief = relief[65, 65]
    flat_relief = relief[10, 10]
    assert edge_relief > flat_relief
    # Pure interior of plateau should have zero relief
    assert center_relief < 1.0


def test_local_relief_shape_matches():
    dem = np.random.rand(128, 128) * 1000
    relief = compute_local_relief(dem, window=21)
    assert relief.shape == dem.shape
