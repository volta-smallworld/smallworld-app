from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field, model_validator
from smallworld_api.models.terrain import LatLng, AnalysisWeights

class CompositionType(str, Enum):
    ruleOfThirds = "ruleOfThirds"
    goldenRatio = "goldenRatio"
    leadingLine = "leadingLine"
    symmetry = "symmetry"

class ViewpointSearchRequest(BaseModel):
    center: LatLng
    radiusMeters: float = Field(ge=1000, le=50000)
    weights: AnalysisWeights | None = None
    compositions: list[CompositionType] = Field(
        default=[CompositionType.ruleOfThirds, CompositionType.goldenRatio, CompositionType.leadingLine, CompositionType.symmetry]
    )
    maxViewpoints: int = Field(default=12, ge=1, le=25)
    maxPerScene: int = Field(default=3, ge=1, le=5)

class CameraPose(BaseModel):
    lat: float
    lng: float
    altitudeMeters: float
    headingDegrees: float
    pitchDegrees: float
    rollDegrees: float = 0
    fovDegrees: float = 55

class ViewpointTarget(BaseModel):
    featureId: str
    role: str  # "primary", "secondary", "left", "right", "line", "subject"
    xNorm: float
    yNorm: float

class ViewpointScoreBreakdown(BaseModel):
    viewshedRichness: float
    terrainEntropy: float
    skylineFractal: float
    prospectRefuge: float
    depthLayering: float
    mystery: float
    waterVisibility: float

class ViewpointValidation(BaseModel):
    clearanceMeters: float
    visibleTargetIds: list[str]

class RankedViewpoint(BaseModel):
    id: str
    sceneId: str
    sceneType: str
    composition: CompositionType
    camera: CameraPose
    targets: list[ViewpointTarget]
    distanceMetersApprox: float
    score: float
    scoreBreakdown: ViewpointScoreBreakdown
    validation: ViewpointValidation

class CandidateRejections(BaseModel):
    templateIneligible: int = 0
    noConvergence: int = 0
    underground: int = 0
    occluded: int = 0
    outOfBounds: int = 0

class ViewpointSearchSummary(BaseModel):
    sceneCount: int
    eligibleSceneCount: int
    candidatesGenerated: int
    candidatesRejected: CandidateRejections
    returned: int

class ViewpointRequestEcho(BaseModel):
    center: LatLng
    radiusMeters: float
    zoomUsed: int
    weights: AnalysisWeights
    compositions: list[CompositionType]
    maxViewpoints: int
    maxPerScene: int

class ViewpointSearchResponse(BaseModel):
    request: ViewpointRequestEcho
    summary: ViewpointSearchSummary
    viewpoints: list[RankedViewpoint]
    source: str = "aws-terrarium"
