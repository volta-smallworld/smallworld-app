from pydantic import BaseModel, Field, model_validator


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


# ── Elevation Grid (hour-one) ───────────────────────────────────────────────


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


# ── Analysis (hour-two) ─────────────────────────────────────────────────────


class AnalysisWeights(BaseModel):
    peaks: float = Field(default=1.0, ge=0, le=2)
    ridges: float = Field(default=0.9, ge=0, le=2)
    cliffs: float = Field(default=0.8, ge=0, le=2)
    water: float = Field(default=0.7, ge=0, le=2)
    relief: float = Field(default=1.0, ge=0, le=2)

    @model_validator(mode="after")
    def check_nonzero_sum(self) -> "AnalysisWeights":
        total = self.peaks + self.ridges + self.cliffs + self.water + self.relief
        if total <= 0:
            raise ValueError("Sum of weights must be greater than 0")
        return self


class TerrainAnalysisRequest(BaseModel):
    center: LatLng
    radiusMeters: float = Field(ge=1000, le=50000)
    weights: AnalysisWeights | None = None


class AnalysisRequestEcho(BaseModel):
    center: LatLng
    radiusMeters: float
    zoomUsed: int
    weights: AnalysisWeights


class GridInfo(BaseModel):
    width: int
    height: int
    cellSizeMetersApprox: float


class MetricSummary(BaseModel):
    min: float
    max: float
    mean: float


class AnalysisSummary(BaseModel):
    elevationMeters: MetricSummary
    slopeDegrees: MetricSummary
    localReliefMeters: MetricSummary
    interestScore: MetricSummary


class PointFeature(BaseModel):
    id: str
    center: LatLng
    elevationMeters: float | None = None
    prominenceMetersApprox: float | None = None
    dropMetersApprox: float | None = None
    score: float


class LineFeature(BaseModel):
    id: str
    path: list[LatLng]
    lengthMetersApprox: int
    score: float


class Features(BaseModel):
    peaks: list[PointFeature]
    ridges: list[LineFeature]
    cliffs: list[PointFeature]
    waterChannels: list[LineFeature]


class Hotspot(BaseModel):
    id: str
    center: LatLng
    score: float
    reasons: list[str]


class SceneSeed(BaseModel):
    id: str
    type: str
    center: LatLng
    featureIds: list[str]
    summary: str
    score: float


class TerrainAnalysisResponse(BaseModel):
    request: AnalysisRequestEcho
    bounds: Bounds
    grid: GridInfo
    summary: AnalysisSummary
    features: Features
    hotspots: list[Hotspot]
    scenes: list[SceneSeed]
    tiles: list[TileRef]
    source: str = "aws-terrarium"
