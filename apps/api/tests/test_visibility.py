import math

import numpy as np

from smallworld_api.services.tiles import GeoBounds
from smallworld_api.services.visibility import compute_viewshed, score_viewpoint


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_bounds(center_lat=47.0, center_lng=-122.0, span=0.05):
    """Create a small GeoBounds centred on the given lat/lng."""
    return GeoBounds(
        north=center_lat + span,
        south=center_lat - span,
        east=center_lng + span,
        west=center_lng - span,
    )


# ── compute_viewshed ────────────────────────────────────────────────────────


def test_flat_terrain_mostly_visible():
    """On flat terrain the camera can see nearly every cell."""
    size = 32
    dem = np.full((size, size), 100.0)
    bounds = _make_bounds()
    cam_lat = 47.0
    cam_lng = -122.0
    cam_alt = 110.0  # slightly above the flat surface

    result = compute_viewshed(
        dem, bounds, cam_lat, cam_lng, cam_alt,
        fov_degrees=360.0, heading_degrees=0.0,
        ray_count=72, steps_per_ray=40,
    )

    visible_mask = result["visible_mask"]
    assert visible_mask.shape == (size, size)
    visible_fraction = visible_mask.sum() / visible_mask.size
    # With a 360-degree FOV the majority of the grid should be visible
    assert visible_fraction > 0.5


def test_tall_mountain_blocks_cells_behind_it():
    """A tall wall across the middle should block visibility to the far side."""
    size = 64
    dem = np.full((size, size), 100.0)
    # Place a tall east-west wall across the grid at row 20
    dem[18:22, :] = 5000.0

    bounds = _make_bounds()
    # Camera is in the top portion of the grid (low row = north)
    cam_lat = bounds.north - 0.005
    cam_lng = (bounds.east + bounds.west) / 2
    cam_alt = 110.0

    result = compute_viewshed(
        dem, bounds, cam_lat, cam_lng, cam_alt,
        fov_degrees=180.0, heading_degrees=180.0,  # looking south
        ray_count=60, steps_per_ray=60,
    )

    visible_mask = result["visible_mask"]
    # Cells well beyond the wall (row > 30) should mostly be hidden
    behind_wall = visible_mask[35:, :]
    behind_fraction = behind_wall.sum() / behind_wall.size
    assert behind_fraction < 0.3


def test_viewshed_return_keys():
    """compute_viewshed must return the three documented keys."""
    dem = np.full((32, 32), 100.0)
    bounds = _make_bounds()
    result = compute_viewshed(
        dem, bounds, 47.0, -122.0, 110.0,
        fov_degrees=90.0, heading_degrees=0.0,
    )

    assert "visible_mask" in result
    assert "max_elevation_angles" in result
    assert "visible_distances" in result
    assert result["visible_mask"].dtype == bool
    assert result["max_elevation_angles"].shape == (90,)  # default ray_count


def test_viewshed_visible_distances_are_positive():
    """All distances in visible_distances should be positive."""
    dem = np.full((32, 32), 100.0)
    bounds = _make_bounds()
    result = compute_viewshed(
        dem, bounds, 47.0, -122.0, 110.0,
        fov_degrees=90.0, heading_degrees=0.0,
    )
    for row, col, dist in result["visible_distances"]:
        assert dist > 0


def test_viewshed_single_ray():
    """ray_count=1 should still produce valid output."""
    dem = np.full((32, 32), 100.0)
    bounds = _make_bounds()
    result = compute_viewshed(
        dem, bounds, 47.0, -122.0, 110.0,
        fov_degrees=10.0, heading_degrees=90.0,
        ray_count=1, steps_per_ray=20,
    )
    assert result["max_elevation_angles"].shape == (1,)
    assert result["visible_mask"].shape == (32, 32)


def test_camera_below_surface_sees_less():
    """A camera underground should see far fewer cells than one above."""
    dem = np.full((32, 32), 500.0)
    bounds = _make_bounds()
    result_above = compute_viewshed(
        dem, bounds, 47.0, -122.0, 600.0,
        fov_degrees=360.0, heading_degrees=0.0,
        ray_count=36, steps_per_ray=30,
    )
    result_below = compute_viewshed(
        dem, bounds, 47.0, -122.0, 200.0,
        fov_degrees=360.0, heading_degrees=0.0,
        ray_count=36, steps_per_ray=30,
    )
    above_count = result_above["visible_mask"].sum()
    below_count = result_below["visible_mask"].sum()
    # Both may see cells, but the elevated camera should see at least as many
    assert above_count >= below_count


def test_viewshed_max_distance_limits_reach():
    """Providing a short max_distance should reduce visible cells."""
    dem = np.full((64, 64), 100.0)
    bounds = _make_bounds()
    result_far = compute_viewshed(
        dem, bounds, 47.0, -122.0, 110.0,
        fov_degrees=360.0, heading_degrees=0.0,
        ray_count=36, steps_per_ray=40,
    )
    result_near = compute_viewshed(
        dem, bounds, 47.0, -122.0, 110.0,
        fov_degrees=360.0, heading_degrees=0.0,
        ray_count=36, steps_per_ray=40,
        max_distance_meters=100.0,
    )
    assert result_near["visible_mask"].sum() <= result_far["visible_mask"].sum()


# ── score_viewpoint ─────────────────────────────────────────────────────────


def test_score_viewpoint_returns_all_keys():
    """score_viewpoint must return the 7 component keys plus 'total'."""
    size = 32
    dem = np.full((size, size), 200.0)
    bounds = _make_bounds()
    interest = np.random.rand(size, size)

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=210.0,
        fov_degrees=90.0, heading_degrees=0.0,
        water_channel_points=[],
    )

    expected_keys = {
        "viewshedRichness",
        "terrainEntropy",
        "skylineFractal",
        "prospectRefuge",
        "depthLayering",
        "mystery",
        "waterVisibility",
        "total",
    }
    assert set(scores.keys()) == expected_keys


def test_score_viewpoint_values_in_range():
    """All component scores and total must be in [0, 1]."""
    size = 32
    dem = np.full((size, size), 200.0)
    bounds = _make_bounds()
    interest = np.random.rand(size, size)

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=210.0,
        fov_degrees=120.0, heading_degrees=45.0,
        water_channel_points=[],
    )

    for key, value in scores.items():
        assert 0.0 <= value <= 1.0, f"{key}={value} is out of [0, 1]"


def test_score_viewpoint_flat_terrain_with_uniform_interest():
    """Flat terrain + uniform interest should produce nonzero scores."""
    size = 64
    dem = np.full((size, size), 300.0)
    bounds = _make_bounds()
    interest = np.ones((size, size))

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=310.0,
        fov_degrees=360.0, heading_degrees=0.0,
        water_channel_points=[],
        ray_count=72, steps_per_ray=40,
    )

    # With uniform interest and broad visibility, viewshed richness should be nonzero
    assert scores["viewshedRichness"] > 0.1
    assert scores["total"] > 0.0


def test_score_viewpoint_total_is_weighted_sum():
    """The total score must equal the documented weighted sum of components."""
    size = 32
    # Use varied terrain for more interesting scores
    dem = np.random.RandomState(42).rand(size, size) * 500 + 100
    bounds = _make_bounds()
    interest = np.random.RandomState(7).rand(size, size)

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=400.0,
        fov_degrees=90.0, heading_degrees=0.0,
        water_channel_points=[],
    )

    weights = {
        "viewshedRichness": 0.20,
        "terrainEntropy": 0.15,
        "skylineFractal": 0.20,
        "prospectRefuge": 0.15,
        "depthLayering": 0.10,
        "mystery": 0.10,
        "waterVisibility": 0.10,
    }
    expected_total = sum(scores[k] * weights[k] for k in weights)
    assert abs(scores["total"] - expected_total) < 1e-10


def test_score_viewpoint_water_visibility_with_visible_points():
    """Water points inside the visible area should produce nonzero waterVisibility."""
    size = 32
    dem = np.full((size, size), 100.0)
    bounds = _make_bounds()
    interest = np.ones((size, size))

    # Place water points at the center of the grid (should be visible from above)
    center_lat = (bounds.north + bounds.south) / 2
    center_lng = (bounds.east + bounds.west) / 2
    water_points = [
        {"lat": center_lat, "lng": center_lng},
        {"lat": center_lat + 0.001, "lng": center_lng + 0.001},
    ]

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=center_lat, cam_lng=center_lng, cam_alt=200.0,
        fov_degrees=360.0, heading_degrees=0.0,
        water_channel_points=water_points,
        ray_count=72, steps_per_ray=40,
    )

    assert scores["waterVisibility"] > 0.0


def test_score_viewpoint_no_water_points_gives_zero():
    """Empty water_channel_points should yield waterVisibility=0."""
    size = 32
    dem = np.full((size, size), 100.0)
    bounds = _make_bounds()
    interest = np.ones((size, size))

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=200.0,
        fov_degrees=90.0, heading_degrees=0.0,
        water_channel_points=[],
    )

    assert scores["waterVisibility"] == 0.0


def test_score_viewpoint_zero_interest_raster():
    """An all-zeros interest raster should give viewshedRichness=0."""
    size = 32
    dem = np.full((size, size), 100.0)
    bounds = _make_bounds()
    interest = np.zeros((size, size))

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=200.0,
        fov_degrees=90.0, heading_degrees=0.0,
        water_channel_points=[],
    )

    assert scores["viewshedRichness"] == 0.0


def test_score_viewpoint_varied_terrain_entropy():
    """Terrain with many different elevation values should produce higher entropy
    than perfectly flat terrain."""
    size = 64
    bounds = _make_bounds()
    interest = np.ones((size, size))

    # Flat terrain
    flat_dem = np.full((size, size), 100.0)
    scores_flat = score_viewpoint(
        flat_dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=200.0,
        fov_degrees=360.0, heading_degrees=0.0,
        water_channel_points=[],
        ray_count=72, steps_per_ray=40,
    )

    # Varied terrain (random elevations across a wide range)
    rng = np.random.RandomState(99)
    varied_dem = rng.rand(size, size) * 1000 + 100
    scores_varied = score_viewpoint(
        varied_dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=1500.0,
        fov_degrees=360.0, heading_degrees=0.0,
        water_channel_points=[],
        ray_count=72, steps_per_ray=40,
    )

    assert scores_varied["terrainEntropy"] > scores_flat["terrainEntropy"]


def test_score_viewpoint_prospect_refuge_with_shelter():
    """When nearby cells are above camera altitude, prospect-refuge should be nonzero."""
    size = 64
    bounds = _make_bounds()
    interest = np.ones((size, size))

    # Terrain with hills near the camera
    dem = np.full((size, size), 100.0)
    # Raise the area around the camera position (center of grid)
    dem[28:36, 28:36] = 500.0

    scores = score_viewpoint(
        dem, bounds, interest,
        cam_lat=47.0, cam_lng=-122.0, cam_alt=250.0,
        fov_degrees=360.0, heading_degrees=0.0,
        water_channel_points=[],
        ray_count=72, steps_per_ray=40,
    )

    # There are cells above camera altitude nearby, so refuge > 0
    # and camera can see some cells, so prospect > 0
    assert scores["prospectRefuge"] > 0.0
