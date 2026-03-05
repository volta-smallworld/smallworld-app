import math
from dataclasses import dataclass

# Web Mercator projection is only defined within these latitude bounds.
_MERCATOR_MAX_LAT = 85.051129


@dataclass
class GeoBounds:
    north: float
    south: float
    east: float
    west: float


@dataclass
class TileRange:
    z: int
    x_min: int
    x_max: int
    y_min: int
    y_max: int

    @property
    def tile_count(self) -> int:
        return (self.x_max - self.x_min + 1) * (self.y_max - self.y_min + 1)

    def tile_coords(self) -> list[tuple[int, int, int]]:
        coords = []
        for x in range(self.x_min, self.x_max + 1):
            for y in range(self.y_min, self.y_max + 1):
                coords.append((self.z, x, y))
        return coords


def center_radius_to_bounds(lat: float, lng: float, radius_m: float) -> GeoBounds:
    """Convert a center point and radius in meters to geographic bounds.

    Bounds are clamped to Web Mercator limits (±85.051129° lat, ±180° lng) so
    that all returned coordinates are valid slippy-map tile inputs.  Selections
    near the poles use a conservative longitude spread computed at ±89° rather
    than dividing by cos(±90°) ≈ 0.
    """
    earth_radius = 6378137.0
    d_lat = math.degrees(radius_m / earth_radius)
    # Clamp the reference latitude used for the longitude spread so that
    # cos(lat) never reaches 0 (which would produce infinite d_lng).
    lat_for_lng = max(-89.0, min(89.0, lat))
    d_lng = math.degrees(radius_m / (earth_radius * math.cos(math.radians(lat_for_lng))))
    # Clamp in both directions so that a center beyond Mercator limits never
    # inverts north/south (e.g. lat=90 makes south=89.99 > north=85.051).
    north = max(min(lat + d_lat, _MERCATOR_MAX_LAT), -_MERCATOR_MAX_LAT)
    south = min(max(lat - d_lat, -_MERCATOR_MAX_LAT), _MERCATOR_MAX_LAT)
    east = min(lng + d_lng, 180.0)
    west = max(lng - d_lng, -180.0)
    return GeoBounds(north=north, south=south, east=east, west=west)


def _lat_to_tile_y(lat: float, zoom: int) -> int:
    n = 2**zoom
    lat_rad = math.radians(lat)
    return int(n * (1 - (math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi)) / 2)


def _lng_to_tile_x(lng: float, zoom: int) -> int:
    n = 2**zoom
    return int(n * ((lng + 180) / 360))


def _lat_to_tile_y_frac(lat: float, zoom: int) -> float:
    """Like _lat_to_tile_y but returns the fractional (continuous) tile coordinate."""
    lat = max(-85.05, min(85.05, lat))
    n = 2**zoom
    lat_rad = math.radians(lat)
    return n * (1 - (math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi)) / 2


def _lng_to_tile_x_frac(lng: float, zoom: int) -> float:
    """Like _lng_to_tile_x but returns the fractional (continuous) tile coordinate."""
    n = 2**zoom
    return n * ((lng + 180) / 360)


def bounds_to_tile_range(bounds: GeoBounds, zoom: int) -> TileRange:
    """Convert geographic bounds to a slippy-map tile range at the given zoom."""
    max_idx = 2**zoom - 1
    x_min = max(0, min(_lng_to_tile_x(bounds.west, zoom), max_idx))
    x_max = max(0, min(_lng_to_tile_x(bounds.east, zoom), max_idx))
    # In slippy maps, lower latitudes have higher y values
    y_min = max(0, min(_lat_to_tile_y(bounds.north, zoom), max_idx))
    y_max = max(0, min(_lat_to_tile_y(bounds.south, zoom), max_idx))
    return TileRange(z=zoom, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max)


def tile_bounds(z: int, x: int, y: int) -> GeoBounds:
    """Return the geographic bounds of a single tile."""
    n = 2**z
    west = x / n * 360 - 180
    east = (x + 1) / n * 360 - 180
    north_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    south_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n)))
    north = math.degrees(north_rad)
    south = math.degrees(south_rad)
    return GeoBounds(north=north, south=south, east=east, west=west)
