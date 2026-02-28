import math
from dataclasses import dataclass


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
    """Convert a center point and radius in meters to geographic bounds."""
    earth_radius = 6378137.0
    d_lat = math.degrees(radius_m / earth_radius)
    d_lng = math.degrees(radius_m / (earth_radius * math.cos(math.radians(lat))))
    return GeoBounds(
        north=lat + d_lat,
        south=lat - d_lat,
        east=lng + d_lng,
        west=lng - d_lng,
    )


def _lat_to_tile_y(lat: float, zoom: int) -> int:
    n = 2**zoom
    lat_rad = math.radians(lat)
    return int(n * (1 - (math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi)) / 2)


def _lng_to_tile_x(lng: float, zoom: int) -> int:
    n = 2**zoom
    return int(n * ((lng + 180) / 360))


def bounds_to_tile_range(bounds: GeoBounds, zoom: int) -> TileRange:
    """Convert geographic bounds to a slippy-map tile range at the given zoom."""
    x_min = _lng_to_tile_x(bounds.west, zoom)
    x_max = _lng_to_tile_x(bounds.east, zoom)
    # In slippy maps, lower latitudes have higher y values
    y_min = _lat_to_tile_y(bounds.north, zoom)
    y_max = _lat_to_tile_y(bounds.south, zoom)
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
