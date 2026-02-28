"""
Optimal lighting time computation.

For each viewpoint, compute the best time of day for dramatic light
by sampling sun positions and casting shadows on the DEM.
Shadow casting reuses the same ray-casting as viewshed analysis.
"""

import numpy as np
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import List, Tuple, Optional
from config import (
    SHADOW_RATIO_IDEAL, SUN_ELEVATION_IDEAL_DEG,
    LIGHTING_SAMPLE_INTERVAL_MIN,
)
from log import get_logger

log = get_logger("scoring.lighting")

try:
    from astral import LocationInfo
    from astral.sun import sun, elevation, azimuth
    HAS_ASTRAL = True
except ImportError:
    HAS_ASTRAL = False


@dataclass
class LightingResult:
    """Optimal lighting analysis for a viewpoint."""
    best_time: str  # "7:14 AM"
    best_score: float
    description: str
    secondary_time: Optional[str] = None
    secondary_score: float = 0.0
    timeline: List[Tuple[str, float]] = None  # [(time_str, score), ...]

    def to_dict(self):
        return {
            "best_time": self.best_time,
            "best_score": round(self.best_score, 3),
            "description": self.description,
            "secondary_time": self.secondary_time,
            "secondary_score": round(self.secondary_score, 3),
            "timeline": [(t, round(s, 3)) for t, s in (self.timeline or [])],
        }


def compute_optimal_lighting(
    dem: np.ndarray,
    cam_row: int,
    cam_col: int,
    cam_z: float,
    res_m: float,
    lat: float,
    lng: float,
    viewshed: np.ndarray,
    target_date: date = None,
) -> LightingResult:
    """Compute optimal time of day for dramatic lighting.

    Sample sun positions throughout the day, cast shadows on the DEM,
    and score the shadow pattern within the camera's visible area.
    """
    if target_date is None:
        target_date = date.today()

    log.info(f"Computing lighting at ({cam_row},{cam_col}), "
             f"lat={lat:.4f} lng={lng:.4f}, date={target_date}")

    # Get sunrise/sunset times
    sunrise_time, sunset_time = _get_sun_times(lat, lng, target_date)
    log.debug(f"Sun times: rise={sunrise_time}, set={sunset_time}")

    # Sample sun positions
    interval = timedelta(minutes=LIGHTING_SAMPLE_INTERVAL_MIN)
    current = sunrise_time
    timeline = []

    while current <= sunset_time:
        sun_el = _sun_elevation(lat, lng, current)
        sun_az = _sun_azimuth(lat, lng, current)

        if sun_el > 0:  # sun is above horizon
            shadow_map = cast_shadows(dem, res_m, sun_az, sun_el)

            score = _score_lighting(
                dem, shadow_map, viewshed, sun_el, sun_az,
                cam_row, cam_col, res_m,
            )

            time_str = current.strftime("%-I:%M %p")
            timeline.append((time_str, score))

        current += interval

    if not timeline:
        return LightingResult(
            best_time="N/A", best_score=0.0,
            description="Unable to compute lighting for this location.",
        )

    # Find best and secondary times
    timeline.sort(key=lambda x: x[1], reverse=True)
    best_time, best_score = timeline[0]

    # Find secondary in opposite part of day (AM vs PM)
    best_is_am = "AM" in best_time
    secondary = None
    for time_str, score in timeline[1:]:
        is_am = "AM" in time_str
        if is_am != best_is_am:
            secondary = (time_str, score)
            break

    # Generate description
    description = _describe_lighting(best_time, best_is_am)

    # Sort timeline chronologically for display
    timeline_sorted = sorted(timeline, key=lambda x: x[0])

    log.info(f"Best lighting: {best_time} (score={best_score:.3f})"
             + (f", secondary: {secondary[0]}" if secondary else ""))

    return LightingResult(
        best_time=best_time,
        best_score=best_score,
        description=description,
        secondary_time=secondary[0] if secondary else None,
        secondary_score=secondary[1] if secondary else 0.0,
        timeline=timeline_sorted,
    )


def cast_shadows(
    dem: np.ndarray,
    res_m: float,
    sun_azimuth_deg: float,
    sun_elevation_deg: float,
) -> np.ndarray:
    """Cast shadows on the DEM from a given sun position.

    Same ray-casting as viewshed, but rays go toward the sun.
    A cell is in shadow if a ray from it toward the sun hits
    higher terrain before reaching the sun angle.

    Returns: boolean mask, True = in shadow.
    """
    h, w = dem.shape
    shadow = np.zeros((h, w), dtype=bool)

    sun_az_rad = np.radians(sun_azimuth_deg)
    sun_el_rad = np.radians(sun_elevation_deg)

    # Direction toward the sun
    dx = np.sin(sun_az_rad)
    dy = -np.cos(sun_az_rad)  # north = -row
    dz_per_step = np.tan(sun_el_rad) * res_m

    max_steps = max(h, w)

    # For efficiency, process a grid of sample points
    # and interpolate (full per-pixel is too slow for real-time)
    step_size = max(1, min(4, int(h / 100)))

    for r in range(0, h, step_size):
        for c in range(0, w, step_size):
            base_z = dem[r, c]
            in_shadow = False

            for step in range(1, max_steps // 2):
                sr = int(r + dy * step)
                sc = int(c + dx * step)

                if not (0 <= sr < h and 0 <= sc < w):
                    break

                sun_height = base_z + dz_per_step * step
                if dem[sr, sc] > sun_height:
                    in_shadow = True
                    break

            if in_shadow:
                # Fill the step_size block
                r_end = min(r + step_size, h)
                c_end = min(c + step_size, w)
                shadow[r:r_end, c:c_end] = True

    return shadow


def _score_lighting(
    dem: np.ndarray,
    shadow_map: np.ndarray,
    viewshed: np.ndarray,
    sun_elevation: float,
    sun_azimuth: float,
    cam_row: int,
    cam_col: int,
    res_m: float,
) -> float:
    """Score a shadow pattern for photographic quality."""
    visible_cells = viewshed.sum()
    if visible_cells < 10:
        return 0.0

    # 1. Shadow/light ratio (ideal ~35%)
    shadow_in_view = (shadow_map & viewshed).sum()
    shadow_ratio = shadow_in_view / visible_cells
    ratio_score = np.exp(-0.5 * ((shadow_ratio - SHADOW_RATIO_IDEAL) / 0.15) ** 2)

    # 2. Sun elevation (ideal ~8° for golden hour)
    elev_score = np.exp(-0.5 * ((sun_elevation - SUN_ELEVATION_IDEAL_DEG) / 10) ** 2)

    # 3. Peak-lit / valley-shadow contrast
    visible_rows, visible_cols = np.where(viewshed)
    if len(visible_rows) > 0:
        elevations = dem[visible_rows, visible_cols]
        shadows = shadow_map[visible_rows, visible_cols]

        # Correlation between high elevation and being lit (not shadow)
        lit = ~shadows
        if elevations.std() > 0:
            correlation = np.corrcoef(elevations.astype(float), lit.astype(float))[0, 1]
            contrast_score = max(0, correlation)  # positive = peaks lit, valleys dark
        else:
            contrast_score = 0.0
    else:
        contrast_score = 0.0

    # Weighted combination
    return (
        0.35 * ratio_score +
        0.30 * elev_score +
        0.35 * contrast_score
    )


def _get_sun_times(lat: float, lng: float, d: date) -> Tuple[datetime, datetime]:
    """Get sunrise and sunset times for a location and date."""
    if HAS_ASTRAL:
        loc = LocationInfo(latitude=lat, longitude=lng)
        s = sun(loc.observer, date=d)
        return s["sunrise"], s["sunset"]
    else:
        # Approximate: 6 AM to 6 PM
        base = datetime(d.year, d.month, d.day)
        return base.replace(hour=6), base.replace(hour=18)


def _sun_elevation(lat: float, lng: float, dt: datetime) -> float:
    """Get sun elevation angle in degrees."""
    if HAS_ASTRAL:
        loc = LocationInfo(latitude=lat, longitude=lng)
        return elevation(loc.observer, dt)
    else:
        # Simple approximation
        hour = dt.hour + dt.minute / 60
        return max(0, 45 * np.sin(np.pi * (hour - 6) / 12))


def _sun_azimuth(lat: float, lng: float, dt: datetime) -> float:
    """Get sun azimuth angle in degrees (0=N, 90=E)."""
    if HAS_ASTRAL:
        loc = LocationInfo(latitude=lat, longitude=lng)
        return azimuth(loc.observer, dt)
    else:
        hour = dt.hour + dt.minute / 60
        return 90 + (hour - 6) * 15  # rough: east at sunrise, west at sunset


def _describe_lighting(time_str: str, is_morning: bool) -> str:
    """Generate a photographer-friendly lighting description."""
    direction = "eastern" if is_morning else "western"
    period = "morning" if is_morning else "evening"
    return (
        f"Low-angle {direction} light creates dramatic shadows. "
        f"Best {period} conditions — peaks illuminated with valleys in shadow."
    )
