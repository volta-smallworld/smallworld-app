"""Viewshed computation and proxy beauty scoring from a DEM grid."""

from __future__ import annotations

import math

import numpy as np

from smallworld_api.services.tiles import GeoBounds

EARTH_RADIUS = 6378137.0


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------


def _latlng_to_rowcol(
    lat: float, lng: float, bounds: GeoBounds, h: int, w: int
) -> tuple[float, float]:
    """Convert lat/lng to fractional (row, col) in the grid."""
    row = (bounds.north - lat) / (bounds.north - bounds.south) * (h - 1)
    col = (lng - bounds.west) / (bounds.east - bounds.west) * (w - 1)
    return (row, col)


def _step_along_azimuth(
    cam_lat: float, cam_lng: float, azimuth_rad: float, distance: float
) -> tuple[float, float]:
    """Step from a point along an azimuth by a given distance in meters.

    Returns (new_lat, new_lng) in degrees.
    """
    cam_lat_rad = math.radians(cam_lat)
    new_lat = cam_lat + (distance * math.cos(azimuth_rad)) / EARTH_RADIUS * (180 / math.pi)
    new_lng = cam_lng + (distance * math.sin(azimuth_rad)) / (
        EARTH_RADIUS * math.cos(cam_lat_rad)
    ) * (180 / math.pi)
    return (new_lat, new_lng)


def _bounds_diagonal_meters(bounds: GeoBounds) -> float:
    """Approximate diagonal distance of the bounds in meters."""
    dlat = math.radians(bounds.north - bounds.south)
    dlng = math.radians(bounds.east - bounds.west)
    mid_lat = math.radians((bounds.north + bounds.south) / 2)
    dx = dlng * math.cos(mid_lat) * EARTH_RADIUS
    dy = dlat * EARTH_RADIUS
    return math.sqrt(dx * dx + dy * dy)


# ---------------------------------------------------------------------------
# Viewshed
# ---------------------------------------------------------------------------


def compute_viewshed(
    dem: np.ndarray,
    bounds: GeoBounds,
    cam_lat: float,
    cam_lng: float,
    cam_alt: float,
    fov_degrees: float,
    heading_degrees: float,
    ray_count: int = 90,
    steps_per_ray: int = 40,
    max_distance_meters: float | None = None,
) -> dict:
    """Compute which cells are visible from a camera position.

    Casts *ray_count* rays evenly across the horizontal field of view and
    marches outward in *steps_per_ray* distance steps.  A cell is visible when
    its elevation angle (from the camera) exceeds the running maximum along
    that ray.

    Returns a dict with:
    - ``visible_mask``: bool ndarray (h, w) — True for visible cells
    - ``max_elevation_angles``: float ndarray (ray_count,) — peak elevation
      angle per ray (for skyline extraction)
    - ``visible_distances``: list of (row, col, distance_meters) tuples
    """
    h, w = dem.shape

    if max_distance_meters is None:
        max_distance_meters = _bounds_diagonal_meters(bounds)

    visible_mask = np.zeros((h, w), dtype=bool)
    max_elevation_angles = np.full(ray_count, -math.pi / 2, dtype=np.float64)
    visible_distances: list[tuple[int, int, float]] = []

    # Pre-compute azimuth angles spread evenly across the FOV
    half_fov = fov_degrees / 2.0
    start_az = heading_degrees - half_fov
    end_az = heading_degrees + half_fov

    for ray_idx in range(ray_count):
        if ray_count > 1:
            azimuth_deg = start_az + (end_az - start_az) * ray_idx / (ray_count - 1)
        else:
            azimuth_deg = heading_degrees
        azimuth_rad = math.radians(azimuth_deg)

        current_max_angle = -math.pi / 2

        for step in range(1, steps_per_ray + 1):
            distance = max_distance_meters * step / steps_per_ray

            new_lat, new_lng = _step_along_azimuth(cam_lat, cam_lng, azimuth_rad, distance)

            # Convert to grid coordinates
            row_f, col_f = _latlng_to_rowcol(new_lat, new_lng, bounds, h, w)
            row = int(round(row_f))
            col = int(round(col_f))

            # Skip if outside the grid
            if row < 0 or row >= h or col < 0 or col >= w:
                continue

            cell_elev = float(dem[row, col])
            elev_diff = cell_elev - cam_alt

            # Elevation angle from camera to cell
            if distance > 0:
                elev_angle = math.atan2(elev_diff, distance)
            else:
                elev_angle = math.pi / 2 if elev_diff > 0 else -math.pi / 2

            if elev_angle > current_max_angle:
                # Cell is visible
                visible_mask[row, col] = True
                visible_distances.append((row, col, distance))
                current_max_angle = elev_angle

        max_elevation_angles[ray_idx] = current_max_angle

    return {
        "visible_mask": visible_mask,
        "max_elevation_angles": max_elevation_angles,
        "visible_distances": visible_distances,
    }


# ---------------------------------------------------------------------------
# Individual score components
# ---------------------------------------------------------------------------


def _score_viewshed_richness(
    interest_raster: np.ndarray, visible_mask: np.ndarray
) -> float:
    """Fraction of total interest that falls within visible cells."""
    total_interest = float(interest_raster.sum())
    if total_interest <= 0:
        return 0.0
    visible_interest = float(interest_raster[visible_mask].sum())
    return max(0.0, min(1.0, visible_interest / total_interest))


def _score_terrain_entropy(dem: np.ndarray, visible_mask: np.ndarray) -> float:
    """Shannon entropy of visible elevation distribution, binned into 8 bins."""
    visible_elevs = dem[visible_mask]
    if len(visible_elevs) == 0:
        return 0.0

    counts, _ = np.histogram(visible_elevs, bins=8)
    total = counts.sum()
    if total == 0:
        return 0.0

    probs = counts / total
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log(p)

    # Normalize by max possible entropy (log(8))
    max_entropy = math.log(8)
    if max_entropy <= 0:
        return 0.0
    return entropy / max_entropy


def _score_skyline_fractal(max_elevation_angles: np.ndarray) -> float:
    """Fractal dimension score of the skyline profile.

    Uses inline box-counting and a Gaussian score centered at FD=1.3.
    """
    profile = max_elevation_angles
    n = len(profile)
    if n < 4:
        return 0.0

    # Normalize profile to [0, 1]
    mn, mx = float(profile.min()), float(profile.max())
    if mx - mn < 1e-12:
        return 0.0
    normed = (profile - mn) / (mx - mn)

    # Box-counting fractal dimension
    sizes: list[int] = []
    counts: list[int] = []

    s = 2
    while s <= n // 2:
        box_size = s / n
        total_boxes = 0
        for i in range(0, n, s):
            segment = normed[i : min(i + s, n)]
            if len(segment) == 0:
                continue
            y_min = float(segment.min())
            y_max = float(segment.max())
            j_min = int(math.floor(y_min / box_size))
            j_max = int(math.floor(y_max / box_size))
            total_boxes += j_max - j_min + 1
        if total_boxes > 0:
            sizes.append(s)
            counts.append(total_boxes)
        s *= 2

    if len(sizes) < 2:
        fd = 1.0
    else:
        log_inv_size = np.array([math.log(n / s) for s in sizes])
        log_count = np.array([math.log(c) for c in counts])
        coeffs = np.polyfit(log_inv_size, log_count, 1)
        fd = float(coeffs[0])

    # Gaussian score centered at 1.3
    return math.exp(-((fd - 1.3) ** 2) / (2 * 0.15**2))


def _score_prospect_refuge(
    dem: np.ndarray,
    bounds: GeoBounds,
    visible_mask: np.ndarray,
    cam_lat: float,
    cam_lng: float,
    cam_alt: float,
) -> float:
    """Harmonic mean of prospect (visibility fraction) and refuge (nearby shelter)."""
    h, w = dem.shape
    total_cells = h * w

    # Prospect: fraction of cells in viewshed that are visible
    prospect = float(visible_mask.sum()) / total_cells if total_cells > 0 else 0.0

    # Refuge: fraction of cells within 500m of camera that are above camera altitude
    # Convert 500m to approximate grid cells
    lat_span = bounds.north - bounds.south
    lng_span = bounds.east - bounds.west
    mid_lat_rad = math.radians((bounds.north + bounds.south) / 2)

    meters_per_row = lat_span * math.pi / 180 * EARTH_RADIUS / (h - 1) if h > 1 else 1.0
    meters_per_col = (
        lng_span * math.cos(mid_lat_rad) * math.pi / 180 * EARTH_RADIUS / (w - 1)
        if w > 1
        else 1.0
    )

    radius_rows = int(math.ceil(500.0 / meters_per_row)) if meters_per_row > 0 else 0
    radius_cols = int(math.ceil(500.0 / meters_per_col)) if meters_per_col > 0 else 0

    cam_row_f, cam_col_f = _latlng_to_rowcol(cam_lat, cam_lng, bounds, h, w)
    cam_row = int(round(cam_row_f))
    cam_col = int(round(cam_col_f))

    r_min = max(0, cam_row - radius_rows)
    r_max = min(h - 1, cam_row + radius_rows)
    c_min = max(0, cam_col - radius_cols)
    c_max = min(w - 1, cam_col + radius_cols)

    neighborhood = dem[r_min : r_max + 1, c_min : c_max + 1]
    total_neighbors = neighborhood.size
    if total_neighbors == 0:
        refuge = 0.0
    else:
        above_count = int((neighborhood > cam_alt).sum())
        refuge = above_count / total_neighbors

    # Harmonic mean
    if prospect > 0 and refuge > 0:
        return 2.0 * prospect * refuge / (prospect + refuge)
    return 0.0


def _score_depth_layering(
    interest_raster: np.ndarray,
    visible_distances: list[tuple[int, int, float]],
) -> float:
    """Entropy of interest distributed across near/mid/far depth bands."""
    if not visible_distances:
        return 0.0

    max_dist = max(d for _, _, d in visible_distances)
    if max_dist <= 0:
        return 0.0

    # Split into 3 bands
    band_interest = [0.0, 0.0, 0.0]
    for row, col, dist in visible_distances:
        fraction = dist / max_dist
        if fraction < 1.0 / 3.0:
            band = 0
        elif fraction < 2.0 / 3.0:
            band = 1
        else:
            band = 2
        band_interest[band] += float(interest_raster[row, col])

    total = sum(band_interest)
    if total <= 0:
        return 0.0

    probs = [b / total for b in band_interest]
    entropy = 0.0
    for p in probs:
        if p > 0:
            entropy -= p * math.log(p)

    max_entropy = math.log(3)
    if max_entropy <= 0:
        return 0.0
    return entropy / max_entropy


def _score_mystery(
    dem: np.ndarray,
    bounds: GeoBounds,
    interest_raster: np.ndarray,
    visible_mask: np.ndarray,
    cam_lat: float,
    cam_lng: float,
    fov_degrees: float,
    heading_degrees: float,
    ray_count: int,
    steps_per_ray: int,
    max_distance_meters: float | None,
) -> float:
    """Score for high-interest content lurking just beyond visible boundaries."""
    h, w = dem.shape

    if max_distance_meters is None:
        max_distance_meters = _bounds_diagonal_meters(bounds)

    # Determine the interest threshold (top 25th percentile)
    interest_threshold = float(np.percentile(interest_raster, 75))

    total_visible_high_interest = int(
        (visible_mask & (interest_raster >= interest_threshold)).sum()
    )
    if total_visible_high_interest == 0:
        return 0.0

    half_fov = fov_degrees / 2.0
    start_az = heading_degrees - half_fov
    end_az = heading_degrees + half_fov

    mystery_count = 0

    for ray_idx in range(ray_count):
        if ray_count > 1:
            azimuth_deg = start_az + (end_az - start_az) * ray_idx / (ray_count - 1)
        else:
            azimuth_deg = heading_degrees
        azimuth_rad = math.radians(azimuth_deg)

        # Find the last visible step along this ray
        last_visible_step = -1
        for step in range(1, steps_per_ray + 1):
            distance = max_distance_meters * step / steps_per_ray
            new_lat, new_lng = _step_along_azimuth(cam_lat, cam_lng, azimuth_rad, distance)
            row_f, col_f = _latlng_to_rowcol(new_lat, new_lng, bounds, h, w)
            row = int(round(row_f))
            col = int(round(col_f))
            if 0 <= row < h and 0 <= col < w and visible_mask[row, col]:
                last_visible_step = step

        if last_visible_step < 1:
            continue

        # Check cells just behind the last visible cell (next step)
        next_step = last_visible_step + 1
        if next_step > steps_per_ray:
            continue

        distance = max_distance_meters * next_step / steps_per_ray
        new_lat, new_lng = _step_along_azimuth(cam_lat, cam_lng, azimuth_rad, distance)
        row_f, col_f = _latlng_to_rowcol(new_lat, new_lng, bounds, h, w)
        row = int(round(row_f))
        col = int(round(col_f))

        if 0 <= row < h and 0 <= col < w:
            if interest_raster[row, col] >= interest_threshold:
                mystery_count += 1

    return max(0.0, min(1.0, mystery_count / total_visible_high_interest))


def _score_water_visibility(
    visible_mask: np.ndarray,
    bounds: GeoBounds,
    water_channel_points: list[dict],
) -> float:
    """Fraction of water channel points that fall within the visible mask."""
    if not water_channel_points:
        return 0.0

    h, w = visible_mask.shape
    total_water = len(water_channel_points)
    visible_water = 0

    for pt in water_channel_points:
        row_f, col_f = _latlng_to_rowcol(pt["lat"], pt["lng"], bounds, h, w)
        row = int(round(row_f))
        col = int(round(col_f))
        if 0 <= row < h and 0 <= col < w and visible_mask[row, col]:
            visible_water += 1

    return visible_water / total_water


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "viewshedRichness": 0.20,
    "terrainEntropy": 0.15,
    "skylineFractal": 0.20,
    "prospectRefuge": 0.15,
    "depthLayering": 0.10,
    "mystery": 0.10,
    "waterVisibility": 0.10,
}


def score_viewpoint(
    dem: np.ndarray,
    bounds: GeoBounds,
    interest_raster: np.ndarray,
    cam_lat: float,
    cam_lng: float,
    cam_alt: float,
    fov_degrees: float,
    heading_degrees: float,
    water_channel_points: list[dict],
    ray_count: int = 90,
    steps_per_ray: int = 40,
) -> dict:
    """Compute all 7 proxy beauty scores for a viewpoint.

    Returns a dict with keys matching :class:`ViewpointScoreBreakdown` plus a
    ``total`` key with the weighted sum.
    """
    viewshed = compute_viewshed(
        dem,
        bounds,
        cam_lat,
        cam_lng,
        cam_alt,
        fov_degrees,
        heading_degrees,
        ray_count=ray_count,
        steps_per_ray=steps_per_ray,
    )
    visible_mask = viewshed["visible_mask"]
    max_elevation_angles = viewshed["max_elevation_angles"]
    visible_distances = viewshed["visible_distances"]

    scores: dict[str, float] = {}

    scores["viewshedRichness"] = _score_viewshed_richness(interest_raster, visible_mask)
    scores["terrainEntropy"] = _score_terrain_entropy(dem, visible_mask)
    scores["skylineFractal"] = _score_skyline_fractal(max_elevation_angles)
    scores["prospectRefuge"] = _score_prospect_refuge(
        dem, bounds, visible_mask, cam_lat, cam_lng, cam_alt
    )
    scores["depthLayering"] = _score_depth_layering(interest_raster, visible_distances)
    scores["mystery"] = _score_mystery(
        dem,
        bounds,
        interest_raster,
        visible_mask,
        cam_lat,
        cam_lng,
        fov_degrees,
        heading_degrees,
        ray_count,
        steps_per_ray,
        None,
    )
    scores["waterVisibility"] = _score_water_visibility(
        visible_mask, bounds, water_channel_points
    )

    scores["total"] = sum(scores[k] * _WEIGHTS[k] for k in _WEIGHTS)

    return scores
