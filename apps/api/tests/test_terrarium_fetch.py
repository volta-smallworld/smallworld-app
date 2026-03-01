from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from smallworld_api.services.terrarium import GRID_SIZE, fetch_dem_snapshot
from smallworld_api.services.tiles import GeoBounds


@pytest.mark.asyncio
@patch("smallworld_api.services.terrarium.crop_and_resample", return_value=np.zeros((GRID_SIZE, GRID_SIZE)))
@patch("smallworld_api.services.terrarium.fetch_and_stitch", new_callable=AsyncMock)
async def test_fetch_dem_snapshot_reduces_zoom_to_fit_tile_cap(mock_fetch_and_stitch, _mock_crop):
    mock_fetch_and_stitch.return_value = (
        np.zeros((256, 256)),
        GeoBounds(north=46.0, south=45.0, east=-122.0, west=-123.0),
    )

    snap = await fetch_dem_snapshot(
        lat=45.52,
        lng=-122.67,
        radius_m=25000,
        zoom=12,
    )

    tile_range = mock_fetch_and_stitch.await_args.args[1]
    assert snap.zoom < 12
    assert tile_range.tile_count <= 36

