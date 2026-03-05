"""MCP-specific Pydantic schemas.

All MCP models use snake_case field names, unlike REST models which use camelCase.
"""

from __future__ import annotations

from enum import Enum

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


# ── Composition enum ─────────────────────────────────────────────────────


class McpCompositionType(str, Enum):
    rule_of_thirds = "rule_of_thirds"
    golden_ratio = "golden_ratio"
    leading_line = "leading_line"
    symmetry = "symmetry"


# Map from REST camelCase to MCP snake_case
_COMPOSITION_TO_MCP = {
    "ruleOfThirds": McpCompositionType.rule_of_thirds,
    "goldenRatio": McpCompositionType.golden_ratio,
    "leadingLine": McpCompositionType.leading_line,
    "symmetry": McpCompositionType.symmetry,
}

# Map from MCP snake_case to REST camelCase
_COMPOSITION_FROM_MCP = {v.value: k for k, v in _COMPOSITION_TO_MCP.items()}


def composition_to_mcp(rest_value: str) -> McpCompositionType:
    """Convert REST camelCase composition to MCP snake_case."""
    return _COMPOSITION_TO_MCP[rest_value]


def composition_from_mcp(mcp_value: str) -> str:
    """Convert MCP snake_case composition to REST camelCase."""
    return _COMPOSITION_FROM_MCP[mcp_value]


# ── Terrain Analyze Area ─────────────────────────────────────────────────


class TerrainAnalyzeAreaInput(BaseModel):
    lat: float = Field(ge=-90, le=90, description="Center latitude")
    lng: float = Field(ge=-180, le=180, description="Center longitude")
    radius_meters: float = Field(ge=1000, le=50000, description="Search radius in meters")
    zoom: int | None = Field(default=None, description="Tile zoom level override")
    include_elevations: bool = Field(default=False, description="Include the 128x128 elevation matrix")


class TerrainAnalyzeAreaResult(BaseModel):
    center: dict
    radius_meters: float
    zoom_used: int
    bounds: dict
    grid: dict
    summary: dict
    features: dict
    hotspots: list[dict]
    scenes: list[dict]
    tiles: list[dict]
    elevations: list[list[float]] | None = None
    source: str = "aws-terrarium"


# ── Terrain Find Viewpoints ──────────────────────────────────────────────


class TerrainFindViewpointsInput(BaseModel):
    lat: float = Field(ge=-90, le=90, description="Center latitude")
    lng: float = Field(ge=-180, le=180, description="Center longitude")
    radius_meters: float = Field(ge=1000, le=50000, description="Search radius in meters")
    weights: dict | None = Field(default=None, description="Analysis weights: peaks, ridges, cliffs, water, relief (0-2 each)")
    compositions: list[McpCompositionType] | None = Field(
        default=None,
        description="Composition types to generate. Defaults to all four.",
    )
    max_viewpoints: int = Field(default=12, ge=1, le=25, description="Maximum viewpoints to return")
    max_per_scene: int = Field(default=3, ge=1, le=5, description="Maximum viewpoints per scene")
    include_preview_input: bool = Field(default=True, description="Include preview_input for each viewpoint")


# ── MCP Camera / Viewpoint types ─────────────────────────────────────────


class McpGeoPosition(BaseModel):
    lat: float
    lng: float
    alt_meters: float


class McpCameraPose(BaseModel):
    position: McpGeoPosition
    heading_deg: float
    pitch_deg: float
    roll_deg: float = 0.0
    fov_deg: float = 55.0


class McpViewpointTarget(BaseModel):
    feature_id: str
    role: str
    x_norm: float
    y_norm: float


class McpScoreBreakdown(BaseModel):
    viewshed_richness: float = 0.0
    terrain_entropy: float = 0.0
    skyline_fractal: float = 0.0
    prospect_refuge: float = 0.0
    depth_layering: float = 0.0
    mystery: float = 0.0
    water_visibility: float = 0.0


class McpValidation(BaseModel):
    clearance_meters: float
    visible_target_ids: list[str]


class McpPreviewAnchor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    label: str | None = None
    lat: float
    lng: float
    alt_meters: float = Field(
        validation_alias=AliasChoices("alt_meters", "altMeters")
    )
    desired_normalized_x: float = Field(
        default=0.5,
        ge=0,
        le=1,
        validation_alias=AliasChoices("desired_normalized_x", "desiredNormalizedX"),
    )
    desired_normalized_y: float = Field(
        default=0.5,
        ge=0,
        le=1,
        validation_alias=AliasChoices("desired_normalized_y", "desiredNormalizedY"),
    )


class McpPreviewScene(BaseModel):
    center: dict
    radius_meters: float
    scene_id: str | None = None
    scene_type: str | None = None
    scene_summary: str | None = None
    feature_ids: list[str] | None = None


class McpPreviewComposition(BaseModel):
    target_template: McpCompositionType
    subject_label: str | None = None
    horizon_ratio: float | None = None
    anchors: list[McpPreviewAnchor] | None = None


class McpPreviewInput(BaseModel):
    camera: McpCameraPose
    scene: McpPreviewScene
    composition: McpPreviewComposition


class McpViewpoint(BaseModel):
    id: str
    scene: str
    composition: McpCompositionType
    camera: McpCameraPose
    targets: list[McpViewpointTarget]
    distance_meters_approx: float
    score: float
    score_breakdown: McpScoreBreakdown
    validation: McpValidation
    preview_input: McpPreviewInput | None = None


class McpViewpointsSummary(BaseModel):
    scene_count: int
    eligible_scene_count: int
    candidates_generated: int
    candidates_rejected: dict
    returned: int


class McpViewpointsRequest(BaseModel):
    center: dict
    radius_meters: float
    zoom_used: int
    weights: dict
    compositions: list[McpCompositionType]
    max_viewpoints: int
    max_per_scene: int


class TerrainFindViewpointsResult(BaseModel):
    request: McpViewpointsRequest
    summary: McpViewpointsSummary
    viewpoints: list[McpViewpoint]
    source: str = "aws-terrarium"


# ── Preview Render Pose ──────────────────────────────────────────────────


class McpViewportSpec(BaseModel):
    width: int = Field(default=1536, ge=512, le=4096)
    height: int = Field(default=1024, ge=512, le=4096)


class McpEnhancementOptions(BaseModel):
    enabled: bool = True
    prompt: str | None = None


class PreviewRenderPoseInput(BaseModel):
    camera: McpCameraPose
    scene: McpPreviewScene
    composition: McpPreviewComposition
    viewport: McpViewportSpec | None = Field(default=None, description="Viewport dimensions override")
    enhancement: McpEnhancementOptions | None = Field(default=None, description="Enhancement options override")
    include_images: bool = Field(default=False, description="Include inline image data in response")


# ── Terrain Point Context ────────────────────────────────────────────────


class TerrainPointContextInput(BaseModel):
    lat: float = Field(ge=-90, le=90, description="Latitude of the point")
    lng: float = Field(ge=-180, le=180, description="Longitude of the point")
    camera_altitude_meters: float | None = Field(default=None, description="Optional camera altitude to compute AGL")
    context_radius_meters: float = Field(default=2000, ge=500, le=10000, description="Radius for local terrain context")
    zoom: int | None = Field(default=None, ge=1, le=18, description="Tile zoom level override")


# ── Preview Render Pose (continued) ─────────────────────────────────────


class PreviewArtifactRef(BaseModel):
    local_path: str
    url: str | None = None
    mime_type: str = "image/png"
    width: int
    height: int


class PreviewWarning(BaseModel):
    code: str
    message: str


class PreviewRenderPoseResult(BaseModel):
    id: str
    status: str
    warnings: list[PreviewWarning] = []
    raw_image: PreviewArtifactRef
    enhanced_image: PreviewArtifactRef | None = None
    metadata: dict
    timings_ms: dict
    manifest_path: str
