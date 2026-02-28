import numpy as np

from smallworld_api.services.fractals import (
    box_counting_fd,
    fallback_viewing_distance,
    fractal_score,
    preferred_viewing_distance,
    ridge_profile_from_path,
    smooth_profile,
)
from smallworld_api.services.tiles import GeoBounds


# ── box_counting_fd ─────────────────────────────────────────────────────────


def test_box_counting_fd_short_profile_returns_one():
    """Profile with fewer than 4 samples should return 1.0."""
    assert box_counting_fd(np.array([1.0, 2.0, 3.0])) == 1.0
    assert box_counting_fd(np.array([5.0])) == 1.0
    assert box_counting_fd(np.array([])) == 1.0


def test_box_counting_fd_flat_profile_returns_one():
    """A constant-value profile has no variation, so fd should be 1.0."""
    flat = np.full(128, 500.0)
    assert box_counting_fd(flat) == 1.0


def test_box_counting_fd_noisy_profile_above_one():
    """A random/noisy profile should have fractal dimension > 1.0."""
    rng = np.random.default_rng(42)
    noisy = rng.standard_normal(256)
    fd = box_counting_fd(noisy)
    assert fd > 1.0


def test_box_counting_fd_noisier_has_higher_fd():
    """More noise should generally yield a higher fractal dimension."""
    rng = np.random.default_rng(99)
    # Smooth sine
    x = np.linspace(0, 4 * np.pi, 256)
    smooth_signal = np.sin(x)
    # Same sine plus heavy noise
    noisy_signal = np.sin(x) + rng.standard_normal(256) * 2.0

    fd_smooth = box_counting_fd(smooth_signal)
    fd_noisy = box_counting_fd(noisy_signal)
    assert fd_noisy > fd_smooth


def test_box_counting_fd_linear_ramp():
    """A linearly increasing profile should be close to 1.0 (a line)."""
    ramp = np.linspace(0, 1000, 128)
    fd = box_counting_fd(ramp)
    # Box-counting on a discrete linear ramp yields fd slightly below 1.0
    assert 0.85 <= fd <= 1.15


def test_box_counting_fd_returns_finite():
    """fd should always be a finite number for valid input."""
    rng = np.random.default_rng(7)
    profile = rng.uniform(0, 500, 64)
    fd = box_counting_fd(profile)
    assert np.isfinite(fd)


# ── fractal_score ───────────────────────────────────────────────────────────


def test_fractal_score_at_target_returns_near_one():
    """When fd equals the target, the score should be approximately 1.0."""
    score = fractal_score(1.3, target=1.3)
    assert abs(score - 1.0) < 1e-9


def test_fractal_score_far_from_target_is_low():
    """When fd is far from the target, the score should be much less than 1."""
    score = fractal_score(2.0, target=1.3)
    assert score < 0.5


def test_fractal_score_symmetric():
    """Score should be the same distance above and below the target."""
    above = fractal_score(1.5, target=1.3)
    below = fractal_score(1.1, target=1.3)
    assert abs(above - below) < 1e-9


def test_fractal_score_range_zero_to_one():
    """Score should always be in [0, 1]."""
    for fd in [0.5, 1.0, 1.3, 1.5, 2.0, 3.0]:
        score = fractal_score(fd)
        assert 0.0 <= score <= 1.0


def test_fractal_score_custom_sigma():
    """Narrower sigma should produce a lower score for the same offset."""
    wide = fractal_score(1.5, target=1.3, sigma=0.3)
    narrow = fractal_score(1.5, target=1.3, sigma=0.05)
    assert wide > narrow


# ── smooth_profile ──────────────────────────────────────────────────────────


def test_smooth_profile_preserves_length():
    """Output should have the same number of samples as input."""
    profile = np.random.default_rng(1).standard_normal(64)
    smoothed = smooth_profile(profile, scale_cells=5)
    assert len(smoothed) == len(profile)


def test_smooth_profile_reduces_variance():
    """Smoothing should reduce the variance of a noisy signal."""
    rng = np.random.default_rng(2)
    noisy = rng.standard_normal(128)
    smoothed = smooth_profile(noisy, scale_cells=10)
    assert np.var(smoothed) < np.var(noisy)


def test_smooth_profile_flat_stays_flat():
    """A constant profile should remain constant after smoothing."""
    flat = np.full(64, 42.0)
    smoothed = smooth_profile(flat, scale_cells=5)
    assert np.allclose(smoothed, 42.0, atol=1e-10)


def test_smooth_profile_larger_scale_smoother():
    """Larger scale_cells should produce a smoother (lower variance) result."""
    rng = np.random.default_rng(3)
    noisy = rng.standard_normal(128)
    small_scale = smooth_profile(noisy, scale_cells=3)
    large_scale = smooth_profile(noisy, scale_cells=20)
    assert np.var(large_scale) < np.var(small_scale)


# ── ridge_profile_from_path ────────────────────────────────────────────────


def _make_simple_dem_and_bounds():
    """Create a 10x10 DEM with a linear north-south gradient and matching bounds."""
    dem = np.zeros((10, 10))
    for r in range(10):
        dem[r, :] = 1000.0 - r * 100.0  # north=1000m, south=100m
    bounds = GeoBounds(north=40.0, south=39.0, east=-104.0, west=-105.0)
    return dem, bounds


def test_ridge_profile_single_point():
    """A single-point path should return an array filled with that point's elevation."""
    dem, bounds = _make_simple_dem_and_bounds()
    # Point at the north-west corner => row 0, col 0 => elevation 1000
    path = [{"lat": 40.0, "lng": -105.0}]
    profile = ridge_profile_from_path(path, dem, bounds, num_samples=16)
    assert len(profile) == 16
    assert np.allclose(profile, 1000.0)


def test_ridge_profile_single_point_center():
    """A single point at the center of the DEM should sample the center cell."""
    dem, bounds = _make_simple_dem_and_bounds()
    # Center: lat=39.5, lng=-104.5
    path = [{"lat": 39.5, "lng": -104.5}]
    profile = ridge_profile_from_path(path, dem, bounds, num_samples=8)
    assert len(profile) == 8
    # Compute the expected row/col using the same formula as the source
    h, w = dem.shape
    row = int(round((bounds.north - 39.5) / (bounds.north - bounds.south) * (h - 1)))
    col = int(round((-104.5 - bounds.west) / (bounds.east - bounds.west) * (w - 1)))
    expected_elev = dem[row, col]
    assert np.allclose(profile, expected_elev)


def test_ridge_profile_empty_path():
    """An empty path should return zeros."""
    dem, bounds = _make_simple_dem_and_bounds()
    profile = ridge_profile_from_path([], dem, bounds, num_samples=16)
    # len(path) < 2 and len(path) != 1 => returns np.zeros
    assert len(profile) == 16
    assert np.allclose(profile, 0.0)


def test_ridge_profile_multi_point_known_dem():
    """A path traversing north to south should show decreasing elevation."""
    dem, bounds = _make_simple_dem_and_bounds()
    # Path from north (lat=40) to south (lat=39) along center longitude
    path = [
        {"lat": 40.0, "lng": -104.5},
        {"lat": 39.0, "lng": -104.5},
    ]
    profile = ridge_profile_from_path(path, dem, bounds, num_samples=32)
    assert len(profile) == 32
    # First sample should be higher than last sample
    assert profile[0] > profile[-1]
    # Profile should be monotonically non-increasing (north=high, south=low)
    for i in range(1, len(profile)):
        assert profile[i] <= profile[i - 1] + 1e-6  # allow tiny float tolerance


def test_ridge_profile_horizontal_path():
    """A horizontal (east-west) path on a north-south gradient should be constant."""
    dem, bounds = _make_simple_dem_and_bounds()
    # Horizontal path at fixed latitude (middle of grid)
    path = [
        {"lat": 39.5, "lng": -105.0},
        {"lat": 39.5, "lng": -104.0},
    ]
    profile = ridge_profile_from_path(path, dem, bounds, num_samples=16)
    assert len(profile) == 16
    # All samples at the same latitude => same row => same elevation
    assert np.std(profile) < 1e-6


def test_ridge_profile_coincident_points():
    """If all path points are the same, profile should be constant."""
    dem, bounds = _make_simple_dem_and_bounds()
    path = [
        {"lat": 39.5, "lng": -104.5},
        {"lat": 39.5, "lng": -104.5},
        {"lat": 39.5, "lng": -104.5},
    ]
    profile = ridge_profile_from_path(path, dem, bounds, num_samples=20)
    assert len(profile) == 20
    assert np.std(profile) < 1e-6


# ── preferred_viewing_distance ─────────────────────────────────────────────


def test_preferred_viewing_distance_in_range():
    """Result must be clamped to [400, 15000]."""
    dem, bounds = _make_simple_dem_and_bounds()
    path = [
        {"lat": 40.0, "lng": -104.5},
        {"lat": 39.0, "lng": -104.5},
    ]
    dist = preferred_viewing_distance(path, dem, bounds, cell_size_meters=100.0)
    assert 400.0 <= dist <= 15000.0


def test_preferred_viewing_distance_single_point_path():
    """Even with a single-point path, the function should return a valid distance."""
    dem, bounds = _make_simple_dem_and_bounds()
    path = [{"lat": 39.5, "lng": -104.5}]
    dist = preferred_viewing_distance(path, dem, bounds, cell_size_meters=100.0)
    assert 400.0 <= dist <= 15000.0


def test_preferred_viewing_distance_custom_scales():
    """Custom scales should be used instead of defaults."""
    dem, bounds = _make_simple_dem_and_bounds()
    path = [
        {"lat": 40.0, "lng": -104.5},
        {"lat": 39.0, "lng": -104.5},
    ]
    # Using very small scales should produce a smaller distance
    small_dist = preferred_viewing_distance(
        path, dem, bounds, cell_size_meters=100.0, scales_meters=[50, 100]
    )
    # Using very large scales should produce a larger distance
    large_dist = preferred_viewing_distance(
        path, dem, bounds, cell_size_meters=100.0, scales_meters=[5000, 10000]
    )
    assert small_dist < large_dist
    assert 400.0 <= small_dist <= 15000.0
    assert 400.0 <= large_dist <= 15000.0


def test_preferred_viewing_distance_returns_finite():
    """Distance should always be finite."""
    dem, bounds = _make_simple_dem_and_bounds()
    path = [
        {"lat": 40.0, "lng": -105.0},
        {"lat": 39.5, "lng": -104.5},
        {"lat": 39.0, "lng": -104.0},
    ]
    dist = preferred_viewing_distance(path, dem, bounds, cell_size_meters=78.0)
    assert np.isfinite(dist)


# ── fallback_viewing_distance ──────────────────────────────────────────────


def test_fallback_viewing_distance_in_range():
    """Result must be in [400, 15000] for typical extents."""
    dist = fallback_viewing_distance(1000.0)
    assert 400.0 <= dist <= 15000.0


def test_fallback_viewing_distance_minimum_clamp():
    """A very small extent should still return at least 400."""
    dist = fallback_viewing_distance(10.0)
    assert dist == 400.0


def test_fallback_viewing_distance_maximum_clamp():
    """A very large extent should be clamped to 15000."""
    dist = fallback_viewing_distance(100000.0)
    assert dist == 15000.0


def test_fallback_viewing_distance_respects_multiplier():
    """A higher multiplier should produce a larger distance (within clamp bounds)."""
    low = fallback_viewing_distance(1000.0, multiplier=1.0)
    high = fallback_viewing_distance(1000.0, multiplier=4.0)
    assert high >= low


def test_fallback_viewing_distance_default_multiplier():
    """Default multiplier is 2.5, so 1000m extent => 2500m distance."""
    dist = fallback_viewing_distance(1000.0)
    assert dist == 2500.0


def test_fallback_viewing_distance_zero_extent():
    """Zero extent should return the minimum distance."""
    dist = fallback_viewing_distance(0.0)
    assert dist == 400.0


def test_fallback_viewing_distance_exact_boundary():
    """Extent that yields exactly the max distance should return exactly 15000."""
    # 15000 / 2.5 = 6000
    dist = fallback_viewing_distance(6000.0, multiplier=2.5)
    assert dist == 15000.0
