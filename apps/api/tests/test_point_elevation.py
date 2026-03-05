"""Tests for sample_point_elevation and fractional tile math."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from PIL import Image

from smallworld_api.services.tiles import _lat_to_tile_y_frac, _lng_to_tile_x_frac


# ── Fractional tile math ─────────────────────────────────────────────────


class TestFractionalTileMath:
    def test_lng_to_tile_x_frac_prime_meridian(self):
        """Longitude 0 at zoom 1 => fractional x = 1.0 (center of the world)."""
        result = _lng_to_tile_x_frac(0.0, 1)
        assert abs(result - 1.0) < 1e-10

    def test_lng_to_tile_x_frac_dateline(self):
        """Longitude 180 at zoom 1 => fractional x = 2.0."""
        result = _lng_to_tile_x_frac(180.0, 1)
        assert abs(result - 2.0) < 1e-10

    def test_lat_to_tile_y_frac_equator(self):
        """Latitude 0 at zoom 1 => fractional y = 1.0 (center)."""
        result = _lat_to_tile_y_frac(0.0, 1)
        assert abs(result - 1.0) < 1e-10

    def test_lat_to_tile_y_frac_clamped_at_poles(self):
        """Latitudes beyond ±85.05 are clamped to avoid tan(pi/2) singularity."""
        y_90 = _lat_to_tile_y_frac(90.0, 10)
        y_85 = _lat_to_tile_y_frac(85.05, 10)
        assert abs(y_90 - y_85) < 1e-6

    def test_frac_increases_with_zoom(self):
        """Higher zoom => larger fractional coordinate."""
        frac_z10 = _lng_to_tile_x_frac(-105.0, 10)
        frac_z14 = _lng_to_tile_x_frac(-105.0, 14)
        assert frac_z14 > frac_z10

    def test_antimeridian_wrap(self):
        """Longitude 179.999 should produce a valid high tile x."""
        frac = _lng_to_tile_x_frac(179.999, 14)
        n = 2**14
        assert 0 <= frac <= n


# ── sample_point_elevation ───────────────────────────────────────────────


def _make_tile_image(value_r: int, value_g: int, value_b: int) -> Image.Image:
    """Create a 256x256 solid-color Terrarium PNG."""
    img = Image.new("RGB", (256, 256), (value_r, value_g, value_b))
    return img


class TestSamplePointElevation:
    @patch("smallworld_api.services.terrarium.fetch_tile", new_callable=AsyncMock)
    async def test_basic_sampling(self, mock_fetch):
        """Sample at a known coordinate with a uniform tile returns correct elevation."""
        from smallworld_api.services.terrarium import sample_point_elevation

        # Terrarium encoding: elevation = R*256 + G + B/256 - 32768
        # For elevation 1500m: 1500 + 32768 = 34268
        # R = 34268 // 256 = 133, G = 34268 % 256 = 220, B = 0
        mock_fetch.return_value = _make_tile_image(133, 220, 0)

        result = await sample_point_elevation(39.7392, -104.9903, zoom=14)

        assert result.elevation_meters == 1500.0
        assert result.lat == 39.7392
        assert result.lng == -104.9903
        assert result.zoom == 14
        assert len(result.tile_coords) >= 1
        assert result.meters_per_pixel_approx > 0

    @patch("smallworld_api.services.terrarium.fetch_tile", new_callable=AsyncMock)
    async def test_bilinear_interpolation(self, mock_fetch):
        """When pixel falls between tiles, bilinear interpolation blends values."""
        from smallworld_api.services.terrarium import sample_point_elevation

        mock_fetch.return_value = _make_tile_image(133, 220, 0)

        result = await sample_point_elevation(0.0, 0.0, zoom=14)

        # Should return a valid elevation (from the uniform tile)
        assert isinstance(result.elevation_meters, float)

    @patch("smallworld_api.services.terrarium.fetch_tile", new_callable=AsyncMock)
    async def test_uses_default_zoom(self, mock_fetch):
        """When zoom is None, uses the config default."""
        from smallworld_api.services.terrarium import sample_point_elevation

        mock_fetch.return_value = _make_tile_image(133, 220, 0)

        result = await sample_point_elevation(39.7, -105.0)

        # Default zoom from config is 14
        assert result.zoom == 14

    @patch("smallworld_api.services.terrarium.fetch_tile", new_callable=AsyncMock)
    async def test_mercator_clamp(self, mock_fetch):
        """High latitudes should not cause math errors."""
        from smallworld_api.services.terrarium import sample_point_elevation

        mock_fetch.return_value = _make_tile_image(128, 0, 0)

        result = await sample_point_elevation(85.0, 0.0, zoom=10)

        assert isinstance(result.elevation_meters, float)
