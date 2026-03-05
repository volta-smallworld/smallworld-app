"""Tests for camera safety AGL enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from smallworld_api.services.camera_safety import (
    CameraSafetyResult,
    enforce_agl_floor_dem,
    enforce_agl_floor_precise,
)
from smallworld_api.services.tiles import GeoBounds


# ── enforce_agl_floor_dem ────────────────────────────────────────────────


class TestEnforceAglFloorDem:
    def _make_flat_dem(self, elevation: float = 1000.0) -> tuple[np.ndarray, GeoBounds]:
        dem = np.full((128, 128), elevation, dtype=np.float64)
        bounds = GeoBounds(north=40.0, south=39.0, east=-104.0, west=-105.0)
        return dem, bounds

    def test_no_clamp_when_above_ground(self):
        dem, bounds = self._make_flat_dem(1000.0)
        result = enforce_agl_floor_dem(39.5, -104.5, 1200.0, dem, bounds)

        assert not result.was_clamped
        assert result.effective_alt == 1200.0
        assert result.ground_elev == 1000.0
        assert result.clearance == 200.0

    def test_clamp_when_underground(self):
        dem, bounds = self._make_flat_dem(1000.0)
        result = enforce_agl_floor_dem(39.5, -104.5, 999.0, dem, bounds)

        assert result.was_clamped
        assert result.effective_alt == 1005.0  # ground + default 5m floor
        assert result.original_alt == 999.0
        assert result.clearance == 5.0

    def test_clamp_at_exactly_ground_level(self):
        dem, bounds = self._make_flat_dem(1000.0)
        result = enforce_agl_floor_dem(39.5, -104.5, 1000.0, dem, bounds)

        assert result.was_clamped
        assert result.effective_alt == 1005.0

    def test_custom_floor(self):
        dem, bounds = self._make_flat_dem(1000.0)
        result = enforce_agl_floor_dem(39.5, -104.5, 1008.0, dem, bounds, floor=10.0)

        assert result.was_clamped
        assert result.effective_alt == 1010.0
        assert result.clearance == 10.0

    def test_zero_floor(self):
        dem, bounds = self._make_flat_dem(1000.0)
        result = enforce_agl_floor_dem(39.5, -104.5, 1000.0, dem, bounds, floor=0.0)

        assert not result.was_clamped
        assert result.effective_alt == 1000.0

    def test_clearance_math(self):
        dem, bounds = self._make_flat_dem(500.0)
        result = enforce_agl_floor_dem(39.5, -104.5, 600.0, dem, bounds)

        assert result.clearance == 100.0
        assert not result.was_clamped


# ── enforce_agl_floor_precise ────────────────────────────────────────────


class TestEnforceAglFloorPrecise:
    @patch("smallworld_api.services.camera_safety.sample_point_elevation", new_callable=AsyncMock)
    async def test_no_clamp(self, mock_sample):
        from smallworld_api.services.terrarium import PointElevationResult

        mock_sample.return_value = PointElevationResult(
            elevation_meters=1000.0, lat=39.7, lng=-105.0,
            zoom=14, tile_coords=[(14, 100, 200)], meters_per_pixel_approx=9.5,
        )

        result = await enforce_agl_floor_precise(39.7, -105.0, 1200.0)

        assert not result.was_clamped
        assert result.effective_alt == 1200.0

    @patch("smallworld_api.services.camera_safety.sample_point_elevation", new_callable=AsyncMock)
    async def test_clamp(self, mock_sample):
        from smallworld_api.services.terrarium import PointElevationResult

        mock_sample.return_value = PointElevationResult(
            elevation_meters=1000.0, lat=39.7, lng=-105.0,
            zoom=14, tile_coords=[(14, 100, 200)], meters_per_pixel_approx=9.5,
        )

        result = await enforce_agl_floor_precise(39.7, -105.0, 999.0)

        assert result.was_clamped
        assert result.effective_alt == 1005.0
        assert result.clearance == 5.0

    @patch("smallworld_api.services.camera_safety.sample_point_elevation", new_callable=AsyncMock)
    async def test_custom_zoom(self, mock_sample):
        from smallworld_api.services.terrarium import PointElevationResult

        mock_sample.return_value = PointElevationResult(
            elevation_meters=500.0, lat=39.7, lng=-105.0,
            zoom=12, tile_coords=[(12, 50, 100)], meters_per_pixel_approx=38.0,
        )

        result = await enforce_agl_floor_precise(39.7, -105.0, 480.0, zoom=12)

        assert result.was_clamped
        mock_sample.assert_called_once_with(39.7, -105.0, 12)
