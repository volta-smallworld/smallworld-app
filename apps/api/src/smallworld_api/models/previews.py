from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ── Shared geo types ──────────────────────────────────────────────────────


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class GeoPoint3D(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    altMeters: float


# ── Request models ────────────────────────────────────────────────────────


class CameraPoseInput(BaseModel):
    position: GeoPoint3D
    headingDeg: float = Field(ge=0, le=360)
    pitchDeg: float = Field(ge=-89, le=89)
    rollDeg: float = Field(default=0.0)
    fovDeg: float = Field(default=50.0, ge=15, le=100)


class ViewportSpec(BaseModel):
    width: int = Field(default=1536, ge=512, le=4096)
    height: int = Field(default=1024, ge=512, le=4096)


class SceneContext(BaseModel):
    center: LatLng
    radiusMeters: float = Field(ge=1000, le=50000)
    sceneId: str | None = None
    sceneType: str | None = None
    sceneSummary: str | None = None
    featureIds: list[str] | None = None


class CompositionTemplate(str, Enum):
    RULE_OF_THIRDS = "rule_of_thirds"
    GOLDEN_RATIO = "golden_ratio"
    SYMMETRY = "symmetry"
    LEADING_LINE = "leading_line"
    CUSTOM = "custom"


class CompositionAnchor(BaseModel):
    id: str
    label: str | None = None
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    altMeters: float
    desiredNormalizedX: float = Field(ge=0, le=1)
    desiredNormalizedY: float = Field(ge=0, le=1)


class CompositionRequest(BaseModel):
    targetTemplate: CompositionTemplate
    subjectLabel: str | None = None
    horizonRatio: float | None = Field(default=None, ge=0, le=1)
    anchors: list[CompositionAnchor] | None = None


class EnhancementOptions(BaseModel):
    enabled: bool = True
    prompt: str | None = None


class PreviewRenderRequest(BaseModel):
    camera: CameraPoseInput
    viewport: ViewportSpec = Field(default_factory=ViewportSpec)
    scene: SceneContext
    composition: CompositionRequest
    enhancement: EnhancementOptions = Field(default_factory=EnhancementOptions)


# ── Response models ───────────────────────────────────────────────────────


class ImageArtifact(BaseModel):
    url: str
    mimeType: str = "image/png"
    width: int
    height: int


class CameraMetadata(BaseModel):
    lat: float
    lng: float
    altMeters: float
    headingDeg: float
    pitchDeg: float
    rollDeg: float
    fovDeg: float
    compassDirection: str


class LocationMetadata(BaseModel):
    sceneCenter: LatLng
    radiusMeters: float
    googleMapsUrl: str
    geoUri: str


class SceneMetadata(BaseModel):
    sceneId: str | None = None
    sceneType: str | None = None
    sceneSummary: str | None = None
    featureIds: list[str] | None = None


class CompositionTarget(BaseModel):
    template: str
    subjectLabel: str | None = None
    horizonRatio: float | None = None


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNSUPPORTED_TEMPLATE = "unsupported_template"


class CompositionVerification(BaseModel):
    status: VerificationStatus
    source: str = "geometry_projection_v1"
    template: str | None = None
    passesThreshold: bool | None = None
    meanAnchorErrorPx: float | None = None
    horizonErrorPx: float | None = None
    notes: str | None = None


class CompositionMetadata(BaseModel):
    target: CompositionTarget
    verified: CompositionVerification | None = None


class PreviewMetadata(BaseModel):
    camera: CameraMetadata
    location: LocationMetadata
    scene: SceneMetadata
    composition: CompositionMetadata
    summary: str


class TimingsMs(BaseModel):
    render: int | None = None
    enhancement: int | None = None
    total: int


class PreviewWarning(BaseModel):
    code: str
    message: str


class PreviewRenderResponse(BaseModel):
    id: str
    status: str
    warnings: list[PreviewWarning] = []
    rawImage: ImageArtifact | None = None
    enhancedImage: ImageArtifact | None = None
    metadata: PreviewMetadata
    timingsMs: TimingsMs
