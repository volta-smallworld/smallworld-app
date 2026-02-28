from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class ElevationGridRequest(BaseModel):
    center: LatLng
    radiusMeters: float = Field(ge=1000, le=50000)


class RequestEcho(BaseModel):
    center: LatLng
    radiusMeters: float
    zoomUsed: int


class Bounds(BaseModel):
    north: float
    south: float
    east: float
    west: float


class Grid(BaseModel):
    width: int
    height: int
    cellSizeMetersApprox: float
    elevations: list[list[float]]


class TileRef(BaseModel):
    z: int
    x: int
    y: int


class Stats(BaseModel):
    minElevation: float
    maxElevation: float
    meanElevation: float


class ElevationGridResponse(BaseModel):
    request: RequestEcho
    bounds: Bounds
    grid: Grid
    tiles: list[TileRef]
    stats: Stats
    source: str = "aws-terrarium"
