import math

import numpy as np

from smallworld_api.services.camera_geometry import (
    bilinear_elevation,
    check_line_of_sight,
    compute_heading,
    enu_to_latlng,
    latlng_to_enu,
    pitch_from_horizon_ratio,
    project_to_image,
)
from smallworld_api.services.tiles import GeoBounds


# ── latlng_to_enu / enu_to_latlng ───────────────────────────────────────────


def test_latlng_to_enu_origin_is_zero():
    """Converting the origin itself should return (0, 0)."""
    east, north = latlng_to_enu(40.0, -105.0, 40.0, -105.0)
    assert abs(east) < 1e-6
    assert abs(north) < 1e-6


def test_latlng_to_enu_north_is_positive():
    """A point north of the origin should have positive north value."""
    east, north = latlng_to_enu(40.01, -105.0, 40.0, -105.0)
    assert north > 0
    assert abs(east) < 1e-6


def test_latlng_to_enu_east_is_positive():
    """A point east of the origin should have positive east value."""
    east, north = latlng_to_enu(40.0, -104.99, 40.0, -105.0)
    assert east > 0
    assert abs(north) < 1e-6


def test_latlng_to_enu_known_distance():
    """One degree of latitude is roughly 111,195 m at the equator."""
    _, north = latlng_to_enu(1.0, 0.0, 0.0, 0.0)
    assert abs(north - 111_195) < 200  # within ~200 m tolerance


def test_enu_round_trip():
    """Converting to ENU and back should recover the original lat/lng."""
    origin_lat, origin_lng = 39.7392, -104.9903
    target_lat, target_lng = 39.75, -104.97

    east, north = latlng_to_enu(target_lat, target_lng, origin_lat, origin_lng)
    recovered_lat, recovered_lng = enu_to_latlng(east, north, origin_lat, origin_lng)

    assert abs(recovered_lat - target_lat) < 1e-8
    assert abs(recovered_lng - target_lng) < 1e-8


def test_enu_round_trip_at_equator():
    """Round-trip at the equator where cos(lat)=1."""
    east, north = latlng_to_enu(0.01, 0.01, 0.0, 0.0)
    lat, lng = enu_to_latlng(east, north, 0.0, 0.0)
    assert abs(lat - 0.01) < 1e-8
    assert abs(lng - 0.01) < 1e-8


def test_enu_round_trip_high_latitude():
    """Round-trip at high latitude where cos(lat) is small."""
    east, north = latlng_to_enu(70.01, 25.01, 70.0, 25.0)
    lat, lng = enu_to_latlng(east, north, 70.0, 25.0)
    assert abs(lat - 70.01) < 1e-8
    assert abs(lng - 25.01) < 1e-8


# ── bilinear_elevation ──────────────────────────────────────────────────────


def _make_dem_and_bounds():
    """Create a simple 4x4 DEM grid with known values and matching bounds."""
    # Bounds: lat 40..41, lng -106..-105
    bounds = GeoBounds(north=41.0, south=40.0, east=-105.0, west=-106.0)
    # 4x4 grid: row 0 is north (lat=41), row 3 is south (lat=40)
    dem = np.array(
        [
            [100.0, 200.0, 300.0, 400.0],
            [150.0, 250.0, 350.0, 450.0],
            [200.0, 300.0, 400.0, 500.0],
            [250.0, 350.0, 450.0, 550.0],
        ],
        dtype=np.float64,
    )
    return dem, bounds


def test_bilinear_corner_values():
    """Sampling at grid corners should return exact corner values."""
    dem, bounds = _make_dem_and_bounds()

    # NW corner (row=0, col=0): lat=41, lng=-106
    assert bilinear_elevation(dem, bounds, 41.0, -106.0) == 100.0
    # NE corner (row=0, col=3): lat=41, lng=-105
    assert bilinear_elevation(dem, bounds, 41.0, -105.0) == 400.0
    # SW corner (row=3, col=0): lat=40, lng=-106
    assert bilinear_elevation(dem, bounds, 40.0, -106.0) == 250.0
    # SE corner (row=3, col=3): lat=40, lng=-105
    assert bilinear_elevation(dem, bounds, 40.0, -105.0) == 550.0


def test_bilinear_center_interpolation():
    """Sampling at the midpoint between four cells should average them."""
    dem, bounds = _make_dem_and_bounds()

    # Midpoint between (row=0,col=0), (row=0,col=1), (row=1,col=0), (row=1,col=1)
    # That's row=0.5, col=0.5 => lat = 41 - 0.5/3 * 1 = 40.8333.., lng = -106 + 0.5/3 * 1 = -105.8333..
    mid_lat = 41.0 - (0.5 / 3.0)
    mid_lng = -106.0 + (0.5 / 3.0)
    elev = bilinear_elevation(dem, bounds, mid_lat, mid_lng)
    expected = (100.0 + 200.0 + 150.0 + 250.0) / 4.0  # 175.0
    assert abs(elev - expected) < 1e-6


def test_bilinear_edge_midpoint():
    """Sampling at an edge midpoint (between two cells) should average them."""
    dem, bounds = _make_dem_and_bounds()

    # Mid of row=0 between col=0 and col=1: lat=41 (row=0), lng = midpoint
    mid_lng = -106.0 + (1.0 / 3.0) * 0.5  # col = 0.5 in fractional
    # Actually col = (lng - west) / (east - west) * (w-1)
    # col=0.5 => lng = west + 0.5/(w-1) * (east - west) = -106 + 0.5/3 * 1
    mid_lng = -106.0 + 0.5 / 3.0
    elev = bilinear_elevation(dem, bounds, 41.0, mid_lng)
    expected = (100.0 + 200.0) / 2.0
    assert abs(elev - expected) < 1e-6


def test_bilinear_clamps_outside_bounds():
    """Sampling outside bounds should clamp to the nearest edge."""
    dem, bounds = _make_dem_and_bounds()

    # Far north of bounds should clamp to row=0
    elev = bilinear_elevation(dem, bounds, 42.0, -106.0)
    assert elev == 100.0  # NW corner

    # Far south should clamp to row=3
    elev = bilinear_elevation(dem, bounds, 39.0, -105.0)
    assert elev == 550.0  # SE corner


# ── compute_heading ─────────────────────────────────────────────────────────


def test_heading_north():
    """Due north: from (0,0) to (0,1) should be ~0 degrees."""
    h = compute_heading(0, 0, 0, 1)
    assert abs(h - 0.0) < 1e-6


def test_heading_east():
    """Due east: from (0,0) to (1,0) should be 90 degrees."""
    h = compute_heading(0, 0, 1, 0)
    assert abs(h - 90.0) < 1e-6


def test_heading_south():
    """Due south: from (0,0) to (0,-1) should be 180 degrees."""
    h = compute_heading(0, 0, 0, -1)
    assert abs(h - 180.0) < 1e-6


def test_heading_west():
    """Due west: from (0,0) to (-1,0) should be 270 degrees."""
    h = compute_heading(0, 0, -1, 0)
    assert abs(h - 270.0) < 1e-6


def test_heading_northeast():
    """Northeast: 45 degrees."""
    h = compute_heading(0, 0, 1, 1)
    assert abs(h - 45.0) < 1e-6


def test_heading_always_positive():
    """Heading should be in [0, 360)."""
    h = compute_heading(0, 0, -1, -1)  # southwest = 225
    assert 0 <= h < 360
    assert abs(h - 225.0) < 1e-6


# ── pitch_from_horizon_ratio ───────────────────────────────────────────────


def test_pitch_horizon_at_center():
    """Horizon at 0.5 (center of frame) means pitch = 0 (looking level)."""
    pitch = pitch_from_horizon_ratio(0.5, 60.0)
    assert abs(pitch) < 1e-6


def test_pitch_horizon_below_center():
    """Horizon below center (ratio > 0.5) means looking down (negative pitch)."""
    # ratio=0.5 => pitch=0; ratio > 0.5 => looking down => positive result
    # Actually let's check the math: atan((0.7 - 0.5) * 2 * tan(vfov/2))
    # With fov=60, vfov = 60*9/16 = 33.75
    # pitch = atan(0.4 * tan(16.875 deg)) = atan(0.4 * 0.30335) = atan(0.12134)
    pitch = pitch_from_horizon_ratio(0.7, 60.0)
    assert pitch > 0  # positive angle: horizon pushed down => looking slightly up


def test_pitch_horizon_above_center():
    """Horizon above center (ratio < 0.5) means positive pitch (looking up)."""
    pitch = pitch_from_horizon_ratio(0.3, 60.0)
    assert pitch < 0  # negative: looking down


def test_pitch_symmetry():
    """Pitches for symmetric horizon positions should be equal and opposite."""
    pitch_up = pitch_from_horizon_ratio(0.7, 60.0)
    pitch_down = pitch_from_horizon_ratio(0.3, 60.0)
    assert abs(pitch_up + pitch_down) < 1e-8


def test_pitch_known_value():
    """Verify a specific computed value."""
    fov = 60.0
    vertical_fov = fov * 9 / 16  # 33.75
    # horizon_ratio = 1.0 => pitch = atan((1.0 - 0.5) * 2 * tan(vfov/2))
    #                       = atan(1.0 * tan(16.875 deg))
    #                       = 16.875 degrees
    pitch = pitch_from_horizon_ratio(1.0, 60.0)
    assert abs(pitch - vertical_fov / 2) < 1e-6


# ── project_to_image ────────────────────────────────────────────────────────


def test_project_behind_camera_returns_none():
    """A point behind the camera should return None."""
    # Camera at (0,0) alt=100, heading=0 (north), pitch=0.
    # A point directly south (negative north) is behind the camera.
    result = project_to_image(
        point_enu=(0, -100, 100),
        cam_enu=(0, 0),
        cam_alt=100,
        heading_deg=0,
        pitch_deg=0,
        fov_deg=60,
    )
    assert result is None


def test_project_point_directly_ahead():
    """A point directly in front of the camera should project to center."""
    # Camera at origin, heading north (0 deg), pitch 0.
    # Point directly north at same altitude.
    result = project_to_image(
        point_enu=(0, 1000, 100),
        cam_enu=(0, 0),
        cam_alt=100,
        heading_deg=0,
        pitch_deg=0,
        fov_deg=60,
    )
    assert result is not None
    x, y = result
    assert abs(x - 0.5) < 1e-4  # horizontally centered
    assert abs(y - 0.5) < 1e-4  # vertically centered


def test_project_point_to_the_right():
    """A point to the right of the view should have xNorm > 0.5."""
    # Camera heading north; point to the east (positive east direction).
    result = project_to_image(
        point_enu=(100, 1000, 100),
        cam_enu=(0, 0),
        cam_alt=100,
        heading_deg=0,
        pitch_deg=0,
        fov_deg=60,
    )
    assert result is not None
    x, y = result
    assert x > 0.5


def test_project_point_outside_fov_returns_none():
    """A point far to the side (outside FOV) should return None."""
    result = project_to_image(
        point_enu=(5000, 100, 100),
        cam_enu=(0, 0),
        cam_alt=100,
        heading_deg=0,
        pitch_deg=0,
        fov_deg=60,
    )
    assert result is None


def test_project_point_above_center():
    """A point above camera altitude should appear in upper half (yNorm < 0.5)."""
    result = project_to_image(
        point_enu=(0, 1000, 200),
        cam_enu=(0, 0),
        cam_alt=100,
        heading_deg=0,
        pitch_deg=0,
        fov_deg=60,
    )
    assert result is not None
    x, y = result
    assert abs(x - 0.5) < 1e-4
    assert y < 0.5


# ── check_line_of_sight ────────────────────────────────────────────────────


def test_los_flat_terrain_visible():
    """On flat terrain, line-of-sight between two elevated points should be clear."""
    bounds = GeoBounds(north=41.0, south=40.0, east=-105.0, west=-106.0)
    # Flat DEM at 100 m everywhere.
    dem = np.full((128, 128), 100.0, dtype=np.float64)

    visible = check_line_of_sight(
        dem=dem,
        bounds=bounds,
        cam_lat=40.5,
        cam_lng=-105.5,
        cam_alt=200.0,  # well above terrain
        target_lat=40.8,
        target_lng=-105.2,
        target_alt=200.0,
    )
    assert visible is True


def test_los_mountain_blocking():
    """A tall mountain between camera and target should block line-of-sight."""
    bounds = GeoBounds(north=41.0, south=40.0, east=-105.0, west=-106.0)
    dem = np.full((128, 128), 100.0, dtype=np.float64)

    # Place a mountain ridge in the middle rows (rows 50-70 cover roughly
    # the midpoint between lat 40.3 and 40.7).
    dem[50:70, :] = 5000.0

    visible = check_line_of_sight(
        dem=dem,
        bounds=bounds,
        cam_lat=40.3,
        cam_lng=-105.5,
        cam_alt=200.0,
        target_lat=40.7,
        target_lng=-105.5,
        target_alt=200.0,
    )
    assert visible is False


def test_los_camera_above_mountain():
    """If camera is high enough, it can see over a mountain."""
    bounds = GeoBounds(north=41.0, south=40.0, east=-105.0, west=-106.0)
    dem = np.full((128, 128), 100.0, dtype=np.float64)
    dem[50:70, :] = 500.0  # moderate ridge

    visible = check_line_of_sight(
        dem=dem,
        bounds=bounds,
        cam_lat=40.3,
        cam_lng=-105.5,
        cam_alt=5000.0,  # far above the ridge
        target_lat=40.7,
        target_lng=-105.5,
        target_alt=5000.0,
    )
    assert visible is True


def test_los_target_at_ground_level_blocked():
    """Target at ground level behind a ridge should be blocked."""
    bounds = GeoBounds(north=41.0, south=40.0, east=-105.0, west=-106.0)
    dem = np.full((128, 128), 100.0, dtype=np.float64)
    dem[60:65, :] = 300.0  # small ridge

    visible = check_line_of_sight(
        dem=dem,
        bounds=bounds,
        cam_lat=40.3,
        cam_lng=-105.5,
        cam_alt=150.0,
        target_lat=40.7,
        target_lng=-105.5,
        target_alt=101.0,  # barely above ground
    )
    assert visible is False
