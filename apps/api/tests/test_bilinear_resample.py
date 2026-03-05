"""Tests for bilinear resampling correctness in crop_and_resample.

Validates that the scipy bilinear interpolation (order=1) used by
crop_and_resample produces smooth, accurate outputs for synthetic
DEM gradients and edge cases.
"""

import numpy as np

from smallworld_api.services.terrarium import GRID_SIZE, crop_and_resample
from smallworld_api.services.tiles import GeoBounds


def _make_mosaic_bounds() -> GeoBounds:
    """Return simple mosaic bounds spanning 1 degree in each direction."""
    return GeoBounds(north=40.0, south=39.0, east=-104.0, west=-105.0)


def _make_target_bounds() -> GeoBounds:
    """Return target bounds that crop the center of the mosaic."""
    return GeoBounds(north=39.75, south=39.25, east=-104.25, west=-104.75)


# ── Output shape ──────────────────────────────────────────────────────────


def test_output_is_always_grid_size():
    """Regardless of input size, output must be GRID_SIZE x GRID_SIZE (128x128)."""
    for mosaic_size in [64, 128, 256, 512, 1024]:
        mosaic = np.random.rand(mosaic_size, mosaic_size)
        result = crop_and_resample(
            mosaic, _make_mosaic_bounds(), _make_target_bounds()
        )
        assert result.shape == (GRID_SIZE, GRID_SIZE), (
            f"Expected ({GRID_SIZE}, {GRID_SIZE}), got {result.shape} "
            f"for mosaic size {mosaic_size}"
        )


def test_output_shape_default_grid_size():
    """Default grid_size parameter produces 128x128."""
    mosaic = np.ones((256, 256))
    result = crop_and_resample(mosaic, _make_mosaic_bounds(), _make_target_bounds())
    assert result.shape == (128, 128)


def test_output_shape_custom_grid_size():
    """Custom grid_size is respected."""
    mosaic = np.ones((256, 256))
    result = crop_and_resample(
        mosaic, _make_mosaic_bounds(), _make_target_bounds(), grid_size=64
    )
    assert result.shape == (64, 64)


# ── Bilinear interpolation correctness ────────────────────────────────────


def test_linear_gradient_east_west_preserves_monotonicity():
    """A left-to-right linear gradient should remain monotonically increasing
    after bilinear resample."""
    h, w = 512, 512
    mosaic = np.tile(np.linspace(0, 1000, w), (h, 1))
    result = crop_and_resample(mosaic, _make_mosaic_bounds(), _make_target_bounds())

    # Each row should be monotonically non-decreasing
    for row_idx in range(result.shape[0]):
        row = result[row_idx, :]
        diffs = np.diff(row)
        assert np.all(diffs >= -1e-6), (
            f"Row {row_idx} is not monotonically non-decreasing"
        )


def test_linear_gradient_north_south_preserves_monotonicity():
    """A top-to-bottom linear gradient should remain monotonically increasing
    after bilinear resample (note: row 0 = north = high lat)."""
    h, w = 512, 512
    mosaic = np.tile(np.linspace(0, 1000, h).reshape(-1, 1), (1, w))
    result = crop_and_resample(mosaic, _make_mosaic_bounds(), _make_target_bounds())

    # Each column should be monotonically non-decreasing
    for col_idx in range(result.shape[1]):
        col = result[:, col_idx]
        diffs = np.diff(col)
        assert np.all(diffs >= -1e-6), (
            f"Column {col_idx} is not monotonically non-decreasing"
        )


def test_uniform_mosaic_produces_uniform_output():
    """A uniform elevation mosaic should produce a uniform output."""
    value = 1500.0
    mosaic = np.full((512, 512), value)
    result = crop_and_resample(mosaic, _make_mosaic_bounds(), _make_target_bounds())
    np.testing.assert_allclose(result, value, atol=1e-6)


def test_bilinear_smooths_step_function():
    """A sharp step function should be smoothed (not just nearest-neighbored)
    by bilinear interpolation. The output should contain intermediate values."""
    h, w = 512, 512
    mosaic = np.zeros((h, w))
    mosaic[:, w // 2:] = 1000.0

    result = crop_and_resample(mosaic, _make_mosaic_bounds(), _make_target_bounds())

    unique_vals = np.unique(result)
    # Bilinear interpolation should produce values between 0 and 1000,
    # not just the two discrete values
    assert len(unique_vals) > 2, (
        "Bilinear resample of a step function should produce intermediate values"
    )
    assert np.min(result) >= -1e-6
    assert np.max(result) <= 1000.0 + 1e-6


def test_diagonal_gradient_smooth_transitions():
    """A diagonal gradient should produce smooth transitions in all directions."""
    h, w = 512, 512
    y_vals = np.linspace(0, 500, h).reshape(-1, 1)
    x_vals = np.linspace(0, 500, w).reshape(1, -1)
    mosaic = y_vals + x_vals  # diagonal gradient from 0 to 1000

    result = crop_and_resample(mosaic, _make_mosaic_bounds(), _make_target_bounds())

    # The result should span a reasonable subrange of [0, 1000]
    assert np.min(result) >= 0.0
    assert np.max(result) <= 1000.0 + 1e-6
    # Values should be smoothly distributed (not clustered at extremes)
    mid_count = np.sum((result > 200) & (result < 800))
    assert mid_count > 0, "Diagonal gradient should have mid-range values"


# ── Edge cases ────────────────────────────────────────────────────────────


def test_empty_crop_region_returns_zeros():
    """When target bounds fall entirely outside the mosaic, return zeros."""
    mosaic = np.ones((256, 256)) * 999.0
    mosaic_bounds = GeoBounds(north=40.0, south=39.0, east=-104.0, west=-105.0)
    # Target is entirely east of mosaic
    target_bounds = GeoBounds(north=39.75, south=39.25, east=-100.0, west=-101.0)

    result = crop_and_resample(mosaic, mosaic_bounds, target_bounds)
    assert result.shape == (GRID_SIZE, GRID_SIZE)
    np.testing.assert_array_equal(result, 0.0)


def test_very_small_crop_region():
    """A very small target region should still produce a valid GRID_SIZE output."""
    mosaic = np.random.rand(512, 512) * 1000.0
    mosaic_bounds = GeoBounds(north=40.0, south=39.0, east=-104.0, west=-105.0)
    # Very small target: ~0.01 degree square
    target_bounds = GeoBounds(
        north=39.505, south=39.495, east=-104.495, west=-104.505
    )

    result = crop_and_resample(mosaic, mosaic_bounds, target_bounds)
    assert result.shape == (GRID_SIZE, GRID_SIZE)
    # Should have non-zero values since it overlaps the mosaic
    assert np.any(result != 0.0)


def test_target_equals_mosaic_bounds():
    """When target bounds match mosaic bounds exactly, output should cover
    the full value range."""
    mosaic = np.linspace(0, 1000, 256 * 256).reshape(256, 256)
    bounds = _make_mosaic_bounds()

    result = crop_and_resample(mosaic, bounds, bounds)
    assert result.shape == (GRID_SIZE, GRID_SIZE)
    # Should cover approximately the full range
    assert np.min(result) < 50.0
    assert np.max(result) > 950.0


def test_single_pixel_crop_still_returns_grid():
    """Even when the crop region maps to a single pixel, output should be valid."""
    mosaic = np.full((256, 256), 42.0)
    mosaic_bounds = GeoBounds(north=40.0, south=39.0, east=-104.0, west=-105.0)
    # Very tiny target — approximately 1 pixel in the mosaic
    epsilon = 0.001
    target_bounds = GeoBounds(
        north=39.5 + epsilon, south=39.5 - epsilon,
        east=-104.5 + epsilon, west=-104.5 - epsilon,
    )

    result = crop_and_resample(mosaic, mosaic_bounds, target_bounds)
    assert result.shape == (GRID_SIZE, GRID_SIZE)
