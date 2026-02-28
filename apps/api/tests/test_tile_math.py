from smallworld_api.services.tiles import (
    center_radius_to_bounds,
    bounds_to_tile_range,
)


def test_bounds_shape():
    bounds = center_radius_to_bounds(39.7392, -104.9903, 5000)
    assert bounds.north > 39.7392
    assert bounds.south < 39.7392
    assert bounds.east > -104.9903
    assert bounds.west < -104.9903
    # Roughly symmetric
    assert abs((bounds.north - 39.7392) - (39.7392 - bounds.south)) < 0.0001


def test_bounds_radius_proportional():
    small = center_radius_to_bounds(39.7392, -104.9903, 1000)
    large = center_radius_to_bounds(39.7392, -104.9903, 5000)
    assert (large.north - large.south) > (small.north - small.south)
    assert (large.east - large.west) > (small.east - small.west)


def test_tile_range_at_zoom_12():
    bounds = center_radius_to_bounds(39.7392, -104.9903, 5000)
    tile_range = bounds_to_tile_range(bounds, 12)
    assert tile_range.z == 12
    assert tile_range.x_min <= tile_range.x_max
    assert tile_range.y_min <= tile_range.y_max
    assert tile_range.tile_count > 0
    assert tile_range.tile_count <= 36  # Within our max


def test_tile_coords_count():
    bounds = center_radius_to_bounds(39.7392, -104.9903, 5000)
    tile_range = bounds_to_tile_range(bounds, 12)
    coords = tile_range.tile_coords()
    assert len(coords) == tile_range.tile_count
    for z, x, y in coords:
        assert z == 12


def test_equator_tile_range():
    bounds = center_radius_to_bounds(0.0, 0.0, 2000)
    tile_range = bounds_to_tile_range(bounds, 12)
    assert tile_range.tile_count >= 1
