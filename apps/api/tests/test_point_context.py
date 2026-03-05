"""Tests for point_context service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from smallworld_api.services.tiles import GeoBounds


class TestGetPointContext:
    @patch("smallworld_api.services.point_context.fetch_dem_snapshot", new_callable=AsyncMock)
    @patch("smallworld_api.services.point_context.sample_point_elevation", new_callable=AsyncMock)
    async def test_basic_context(self, mock_sample, mock_dem):
        from smallworld_api.services.point_context import get_point_context
        from smallworld_api.services.terrarium import DEMSnapshot, PointElevationResult

        mock_sample.return_value = PointElevationResult(
            elevation_meters=1500.0, lat=39.7, lng=-105.0,
            zoom=14, tile_coords=[(14, 100, 200)], meters_per_pixel_approx=9.5,
        )

        dem = np.random.uniform(1400, 1600, (128, 128))
        mock_dem.return_value = DEMSnapshot(
            dem=dem,
            bounds=GeoBounds(north=39.72, south=39.68, east=-104.98, west=-105.02),
            tile_coords=[(14, 100, 200)],
            zoom=14,
            cell_size_meters=15.6,
        )

        result = await get_point_context(39.7, -105.0)

        assert result.ground_elevation_meters == 1500.0
        assert result.camera_agl_meters is None
        assert result.sampling["method"] == "bilinear_raw_tile"
        assert result.context is not None
        assert "elevation" in result.context
        assert "slope_degrees" in result.context

    @patch("smallworld_api.services.point_context.fetch_dem_snapshot", new_callable=AsyncMock)
    @patch("smallworld_api.services.point_context.sample_point_elevation", new_callable=AsyncMock)
    async def test_with_camera_altitude(self, mock_sample, mock_dem):
        from smallworld_api.services.point_context import get_point_context
        from smallworld_api.services.terrarium import DEMSnapshot, PointElevationResult

        mock_sample.return_value = PointElevationResult(
            elevation_meters=1500.0, lat=39.7, lng=-105.0,
            zoom=14, tile_coords=[(14, 100, 200)], meters_per_pixel_approx=9.5,
        )

        dem = np.full((128, 128), 1500.0, dtype=np.float64)
        mock_dem.return_value = DEMSnapshot(
            dem=dem,
            bounds=GeoBounds(north=39.72, south=39.68, east=-104.98, west=-105.02),
            tile_coords=[(14, 100, 200)],
            zoom=14,
            cell_size_meters=15.6,
        )

        result = await get_point_context(39.7, -105.0, camera_altitude_meters=1600.0)

        assert result.camera_agl_meters == 100.0

    @patch("smallworld_api.services.point_context.fetch_dem_snapshot", new_callable=AsyncMock)
    @patch("smallworld_api.services.point_context.sample_point_elevation", new_callable=AsyncMock)
    async def test_dem_failure_still_returns_elevation(self, mock_sample, mock_dem):
        from smallworld_api.services.point_context import get_point_context
        from smallworld_api.services.terrarium import PointElevationResult

        mock_sample.return_value = PointElevationResult(
            elevation_meters=1500.0, lat=39.7, lng=-105.0,
            zoom=14, tile_coords=[(14, 100, 200)], meters_per_pixel_approx=9.5,
        )

        mock_dem.side_effect = Exception("Network error")

        result = await get_point_context(39.7, -105.0)

        assert result.ground_elevation_meters == 1500.0
        assert result.context is None
        assert result.sampling["method"] == "bilinear_raw_tile"

    @patch("smallworld_api.services.point_context.fetch_dem_snapshot", new_callable=AsyncMock)
    @patch("smallworld_api.services.point_context.sample_point_elevation", new_callable=AsyncMock)
    async def test_negative_agl(self, mock_sample, mock_dem):
        """Camera below ground level should produce negative AGL."""
        from smallworld_api.services.point_context import get_point_context
        from smallworld_api.services.terrarium import DEMSnapshot, PointElevationResult

        mock_sample.return_value = PointElevationResult(
            elevation_meters=2000.0, lat=39.7, lng=-105.0,
            zoom=14, tile_coords=[(14, 100, 200)], meters_per_pixel_approx=9.5,
        )

        dem = np.full((128, 128), 2000.0, dtype=np.float64)
        mock_dem.return_value = DEMSnapshot(
            dem=dem,
            bounds=GeoBounds(north=39.72, south=39.68, east=-104.98, west=-105.02),
            tile_coords=[(14, 100, 200)],
            zoom=14,
            cell_size_meters=15.6,
        )

        result = await get_point_context(39.7, -105.0, camera_altitude_meters=1800.0)

        assert result.camera_agl_meters == -200.0
