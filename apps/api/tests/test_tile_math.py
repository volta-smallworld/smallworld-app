from smallworld_api.services.tiles import (
    GeoBounds,
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


# ── Edge-case: polar latitudes ───────────────────────────────────────────────


def test_north_pole_does_not_raise():
    """lat=90 must not raise; bounds must be clamped to Mercator limits."""
    bounds = center_radius_to_bounds(90.0, 0.0, 1000)
    assert bounds.north <= 85.051129
    assert bounds.south <= bounds.north
    assert -180.0 <= bounds.west <= bounds.east <= 180.0


def test_south_pole_does_not_raise():
    bounds = center_radius_to_bounds(-90.0, 0.0, 1000)
    assert bounds.south >= -85.051129
    assert bounds.south <= bounds.north
    assert -180.0 <= bounds.west <= bounds.east <= 180.0


def test_polar_tile_range_valid():
    """Tile indices for a polar selection must be within [0, 2^zoom - 1]."""
    bounds = center_radius_to_bounds(90.0, 0.0, 5000)
    tile_range = bounds_to_tile_range(bounds, 12)
    max_idx = 2**12 - 1
    assert 0 <= tile_range.x_min <= tile_range.x_max <= max_idx
    assert 0 <= tile_range.y_min <= tile_range.y_max <= max_idx
    assert tile_range.tile_count >= 1


# ── Edge-case: antimeridian ──────────────────────────────────────────────────


def test_antimeridian_east_does_not_overflow():
    """A selection near lng=180 must not produce tile x >= 2^zoom."""
    bounds = center_radius_to_bounds(0.0, 179.999, 5000)
    assert bounds.east <= 180.0
    tile_range = bounds_to_tile_range(bounds, 12)
    max_idx = 2**12 - 1
    assert 0 <= tile_range.x_min <= tile_range.x_max <= max_idx


def test_antimeridian_west_does_not_underflow():
    """A selection near lng=-180 must not produce negative tile x."""
    bounds = center_radius_to_bounds(0.0, -179.999, 5000)
    assert bounds.west >= -180.0
    tile_range = bounds_to_tile_range(bounds, 12)
    max_idx = 2**12 - 1
    assert 0 <= tile_range.x_min <= tile_range.x_max <= max_idx


def test_bounds_to_tile_range_clamps_explicit_overflow():
    """bounds_to_tile_range must clamp even if caller passes out-of-range bounds."""
    bad_bounds = GeoBounds(north=85.0, south=-85.0, east=181.0, west=-181.0)
    tile_range = bounds_to_tile_range(bad_bounds, 12)
    max_idx = 2**12 - 1
    assert 0 <= tile_range.x_min <= max_idx
    assert 0 <= tile_range.x_max <= max_idx
