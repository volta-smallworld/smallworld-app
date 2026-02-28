from __future__ import annotations
from pydantic import BaseModel, Field
from smallworld_api.models.terrain import LatLng, AnalysisWeights
from smallworld_api.models.viewpoints import (
    CompositionType,
    CameraPose,
    ViewpointTarget,
    ViewpointScoreBreakdown,
    ViewpointValidation,
)


class StyleReferenceCapability(BaseModel):
    enabled: bool
    hedLoaded: bool
    clipLoaded: bool
    lpipsLoaded: bool
    maxUploadBytes: int
    message: str | None = None


class FingerprintSummary(BaseModel):
    dominantOrientationDegrees: float
    edgeDensity: float
    parallelism: float
    verticalCentroid: float
    featureScale: float


class ArtifactFlags(BaseModel):
    edgeMapAvailable: bool


class StyleReferenceUploadResponse(BaseModel):
    referenceId: str
    label: str | None = None
    filename: str
    contentType: str
    width: int
    height: int
    fingerprintSummary: FingerprintSummary
    artifacts: ArtifactFlags


class StyleViewpointSearchRequest(BaseModel):
    center: LatLng
    radiusMeters: float = Field(ge=1000, le=50000)
    weights: AnalysisWeights | None = None
    compositions: list[CompositionType] = Field(
        default=[
            CompositionType.ruleOfThirds,
            CompositionType.goldenRatio,
            CompositionType.leadingLine,
            CompositionType.symmetry,
        ]
    )
    maxViewpoints: int = Field(default=12, ge=1, le=25)
    maxPerScene: int = Field(default=3, ge=1, le=5)
    referenceId: str
    topPatchCount: int = Field(default=24, ge=1, le=100)


class StyleMetadata(BaseModel):
    patchId: str
    matchedFeatureIds: list[str]
    geometrySimilarity: float
    patchSimilarity: float
    contourRefinement: float
    preRenderScore: float
    verificationStatus: str = "pending"
    clipSimilarity: float | None = None
    lpipsDistance: float | None = None
    edgeSimilarity: float | None = None
    finalStyleScore: float | None = None


class StyleRankedViewpoint(BaseModel):
    id: str
    sceneId: str
    sceneType: str
    composition: CompositionType
    camera: CameraPose
    targets: list[ViewpointTarget]
    distanceMetersApprox: float
    baseScore: float
    score: float
    scoreBreakdown: ViewpointScoreBreakdown
    validation: ViewpointValidation
    style: StyleMetadata


class StyleViewpointRequestEcho(BaseModel):
    center: LatLng
    radiusMeters: float
    zoomUsed: int
    weights: AnalysisWeights
    compositions: list[CompositionType]
    maxViewpoints: int
    maxPerScene: int
    referenceId: str
    topPatchCount: int


class StyleReferenceEcho(BaseModel):
    referenceId: str
    label: str | None = None


class StyleSearchRejections(BaseModel):
    templateIneligible: int = 0
    noConvergence: int = 0
    underground: int = 0
    occluded: int = 0
    outOfBounds: int = 0


class StyleViewpointSearchSummary(BaseModel):
    sceneCount: int
    eligibleSceneCount: int
    candidatesGenerated: int
    candidatesRejected: StyleSearchRejections
    patchesScanned: int
    stylePatchMatches: int
    styleCandidatesRefined: int
    returned: int


class StyleViewpointSearchResponse(BaseModel):
    request: StyleViewpointRequestEcho
    reference: StyleReferenceEcho
    summary: StyleViewpointSearchSummary
    viewpoints: list[StyleRankedViewpoint]
    source: str = "aws-terrarium"


class StyleVerificationResult(BaseModel):
    referenceId: str
    viewpointId: str
    verificationStatus: str
    clipSimilarity: float | None = None
    lpipsDistance: float | None = None
    edgeSimilarity: float | None = None
    finalStyleScore: float | None = None
    warnings: list[str] = Field(default_factory=list)
