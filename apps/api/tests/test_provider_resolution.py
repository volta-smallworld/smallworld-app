"""Tests for provider resolution logic and fidelity metadata.

Validates that build_fidelity_dict returns the correct structure
for all key permutations of DEMSnapshot inputs.
"""

import numpy as np

from smallworld_api.services.terrarium import GRID_SIZE, DEMSnapshot, build_fidelity_dict
from smallworld_api.services.tiles import GeoBounds


def _make_snapshot(
    *,
    zoom: int = 12,
    zoom_requested: int = 13,
    tile_count: int = 4,
) -> DEMSnapshot:
    """Create a DEMSnapshot with controllable zoom and tile count."""
    return DEMSnapshot(
        dem=np.random.rand(GRID_SIZE, GRID_SIZE) * 1000,
        bounds=GeoBounds(north=39.8, south=39.7, east=-104.9, west=-105.0),
        tile_coords=[(zoom, i, 1552) for i in range(tile_count)],
        zoom=zoom,
        cell_size_meters=78.0,
        zoom_requested=zoom_requested,
    )


# ── Structure tests ───────────────────────────────────────────────────────


def test_fidelity_dict_has_all_required_fields():
    """build_fidelity_dict must return all 7 documented fidelity fields."""
    snap = _make_snapshot()
    fidelity = build_fidelity_dict(snap)

    expected_keys = {
        "demProvider",
        "zoomRequested",
        "zoomUsed",
        "gridWidth",
        "gridHeight",
        "resampleMethod",
        "tileCount",
    }
    assert set(fidelity.keys()) == expected_keys


def test_fidelity_dict_returns_dict():
    """Return type must be a plain dict (JSON-serializable)."""
    snap = _make_snapshot()
    fidelity = build_fidelity_dict(snap)
    assert isinstance(fidelity, dict)


# ── Field value correctness ───────────────────────────────────────────────


def test_dem_provider_is_terrarium():
    """demProvider should match the config setting (default: 'terrarium')."""
    snap = _make_snapshot()
    fidelity = build_fidelity_dict(snap)
    assert fidelity["demProvider"] == "terrarium"


def test_resample_method_is_bilinear():
    """resampleMethod should always be 'bilinear'."""
    snap = _make_snapshot()
    fidelity = build_fidelity_dict(snap)
    assert fidelity["resampleMethod"] == "bilinear"


def test_grid_dimensions_match_grid_size():
    """gridWidth and gridHeight must both equal GRID_SIZE (128)."""
    snap = _make_snapshot()
    fidelity = build_fidelity_dict(snap)
    assert fidelity["gridWidth"] == GRID_SIZE
    assert fidelity["gridHeight"] == GRID_SIZE
    assert fidelity["gridWidth"] == 128
    assert fidelity["gridHeight"] == 128


def test_zoom_requested_reflects_snapshot():
    """zoomRequested should come from the snapshot's zoom_requested field."""
    snap = _make_snapshot(zoom=11, zoom_requested=13)
    fidelity = build_fidelity_dict(snap)
    assert fidelity["zoomRequested"] == 13


def test_zoom_used_reflects_snapshot():
    """zoomUsed should come from the snapshot's zoom field."""
    snap = _make_snapshot(zoom=11, zoom_requested=13)
    fidelity = build_fidelity_dict(snap)
    assert fidelity["zoomUsed"] == 11


def test_tile_count_reflects_snapshot():
    """tileCount should equal the number of tile_coords in the snapshot."""
    snap = _make_snapshot(tile_count=9)
    fidelity = build_fidelity_dict(snap)
    assert fidelity["tileCount"] == 9


# ── Permutations ──────────────────────────────────────────────────────────


def test_zoom_used_equals_requested_when_no_downshift():
    """When no adaptive downshift occurs, zoom used == zoom requested."""
    snap = _make_snapshot(zoom=13, zoom_requested=13)
    fidelity = build_fidelity_dict(snap)
    assert fidelity["zoomUsed"] == fidelity["zoomRequested"]


def test_zoom_used_less_than_requested_on_downshift():
    """When tiles exceed cap, zoom_used < zoom_requested."""
    snap = _make_snapshot(zoom=10, zoom_requested=13)
    fidelity = build_fidelity_dict(snap)
    assert fidelity["zoomUsed"] < fidelity["zoomRequested"]


def test_single_tile_snapshot():
    """A single-tile snapshot should report tileCount=1."""
    snap = _make_snapshot(zoom=8, zoom_requested=8, tile_count=1)
    fidelity = build_fidelity_dict(snap)
    assert fidelity["tileCount"] == 1
    assert fidelity["zoomUsed"] == 8
    assert fidelity["zoomRequested"] == 8


def test_max_tiles_snapshot():
    """A snapshot at the tile cap should report the correct count."""
    snap = _make_snapshot(zoom=13, zoom_requested=13, tile_count=64)
    fidelity = build_fidelity_dict(snap)
    assert fidelity["tileCount"] == 64


def test_zero_zoom_requested():
    """zoom_requested=0 (default field value) should be reported as-is."""
    snap = DEMSnapshot(
        dem=np.random.rand(GRID_SIZE, GRID_SIZE),
        bounds=GeoBounds(north=39.8, south=39.7, east=-104.9, west=-105.0),
        tile_coords=[(5, 10, 15)],
        zoom=5,
        cell_size_meters=500.0,
        # zoom_requested defaults to 0
    )
    fidelity = build_fidelity_dict(snap)
    assert fidelity["zoomRequested"] == 0
    assert fidelity["zoomUsed"] == 5
