export interface MapSelection {
  lat: number;
  lng: number;
  radiusMeters: number;
}

export interface LatLng {
  lat: number;
  lng: number;
}

export interface ElevationGridRequest {
  center: LatLng;
  radiusMeters: number;
}

// ── Fidelity metadata ────────────────────────────────────────────────────────

export interface Fidelity {
  demProvider?: string;
  zoomRequested?: number;
  zoomUsed?: number;
  gridWidth?: number;
  gridHeight?: number;
  resampleMethod?: string;
  tileCount?: number;
}

export interface ElevationGridResponse {
  request: {
    center: LatLng;
    radiusMeters: number;
    zoomUsed: number;
  };
  bounds: {
    north: number;
    south: number;
    east: number;
    west: number;
  };
  grid: {
    width: number;
    height: number;
    cellSizeMetersApprox: number;
    elevations: number[][];
  };
  tiles: { z: number; x: number; y: number }[];
  stats: {
    minElevation: number;
    maxElevation: number;
    meanElevation: number;
  };
  source: string;
  fidelity?: Fidelity;
}

export type TerrainFetchState = "idle" | "loading" | "success" | "error";

// ── Analysis types (hour-two) ───────────────────────────────────────────────

export interface AnalysisWeights {
  peaks: number;
  ridges: number;
  cliffs: number;
  water: number;
  relief: number;
}

export const DEFAULT_WEIGHTS: AnalysisWeights = {
  peaks: 1.0,
  ridges: 0.9,
  cliffs: 0.8,
  water: 0.7,
  relief: 1.0,
};

export interface TerrainAnalysisRequest {
  center: LatLng;
  radiusMeters: number;
  weights?: AnalysisWeights;
}

export interface MetricSummary {
  min: number;
  max: number;
  mean: number;
}

export interface PointFeature {
  id: string;
  center: LatLng;
  elevationMeters?: number;
  prominenceMetersApprox?: number;
  dropMetersApprox?: number;
  score: number;
}

export interface LineFeature {
  id: string;
  path: LatLng[];
  lengthMetersApprox: number;
  score: number;
}

export interface Hotspot {
  id: string;
  center: LatLng;
  score: number;
  reasons: string[];
}

export interface SceneSeed {
  id: string;
  type: string;
  center: LatLng;
  featureIds: string[];
  summary: string;
  score: number;
}

export interface TerrainAnalysisResponse {
  request: {
    center: LatLng;
    radiusMeters: number;
    zoomUsed: number;
    weights: AnalysisWeights;
  };
  bounds: {
    north: number;
    south: number;
    east: number;
    west: number;
  };
  grid: {
    width: number;
    height: number;
    cellSizeMetersApprox: number;
  };
  summary: {
    elevationMeters: MetricSummary;
    slopeDegrees: MetricSummary;
    localReliefMeters: MetricSummary;
    interestScore: MetricSummary;
  };
  features: {
    peaks: PointFeature[];
    ridges: LineFeature[];
    cliffs: PointFeature[];
    waterChannels: LineFeature[];
  };
  hotspots: Hotspot[];
  scenes: SceneSeed[];
  tiles: { z: number; x: number; y: number }[];
  source: string;
  fidelity?: Fidelity;
}

export type AnalysisOverlayKey =
  | "peaks"
  | "ridges"
  | "cliffs"
  | "waterChannels"
  | "hotspots"
  | "viewpoints";

// ── Viewpoint types (hour-three) ──────────────────────────────────────────────

export type CompositionType = "ruleOfThirds" | "goldenRatio" | "leadingLine" | "symmetry";

export type ViewpointFetchState = "idle" | "loading" | "success" | "error";

export interface ViewpointSearchRequest {
  center: LatLng;
  radiusMeters: number;
  weights?: AnalysisWeights;
  compositions?: CompositionType[];
  maxViewpoints?: number;
  maxPerScene?: number;
}

export interface CameraPose {
  lat: number;
  lng: number;
  altitudeMeters: number;
  headingDegrees: number;
  pitchDegrees: number;
  rollDegrees: number;
  fovDegrees: number;
}

export interface ViewpointTarget {
  featureId: string;
  role: string;
  xNorm: number;
  yNorm: number;
}

export interface ViewpointScoreBreakdown {
  viewshedRichness: number;
  terrainEntropy: number;
  skylineFractal: number;
  prospectRefuge: number;
  depthLayering: number;
  mystery: number;
  waterVisibility: number;
}

export interface RankedViewpoint {
  id: string;
  sceneId: string;
  sceneType: string;
  composition: CompositionType;
  camera: CameraPose;
  targets: ViewpointTarget[];
  distanceMetersApprox: number;
  score: number;
  scoreBreakdown: ViewpointScoreBreakdown;
  validation: {
    clearanceMeters: number;
    visibleTargetIds: string[];
  };
}

export interface ViewpointSearchSummary {
  sceneCount: number;
  eligibleSceneCount: number;
  candidatesGenerated: number;
  candidatesRejected: {
    templateIneligible: number;
    noConvergence: number;
    underground: number;
    occluded: number;
    outOfBounds: number;
  };
  returned: number;
}

export interface ViewpointSearchResponse {
  request: {
    center: LatLng;
    radiusMeters: number;
    zoomUsed: number;
    weights: AnalysisWeights;
    compositions: CompositionType[];
    maxViewpoints: number;
    maxPerScene: number;
  };
  summary: ViewpointSearchSummary;
  viewpoints: RankedViewpoint[];
  source: string;
  fidelity?: Fidelity;
}

// === Hour Four: Preview Types ===

export type ViewpointPreviewStatus = "idle" | "loading" | "ready" | "error" | "unsupported";

export interface PreviewCapability {
  enabled: boolean;
  provider: "ionTerrain" | "google3d" | "none";
  eagerCount: number;
  message: string | null;
}

export interface ViewpointPreviewState {
  status: ViewpointPreviewStatus;
  objectUrl: string | null;
  error: string | null;
}

// === Hour Five: Style Reference Types ===

export type StyleFetchState = "idle" | "loading" | "success" | "error";

export interface StyleReferenceCapability {
  enabled: boolean;
  hedLoaded: boolean;
  clipLoaded: boolean;
  lpipsLoaded: boolean;
  maxUploadBytes: number;
  message: string | null;
}

export interface FingerprintSummary {
  dominantOrientationDegrees: number;
  edgeDensity: number;
  parallelism: number;
  verticalCentroid: number;
  featureScale: number;
}

export interface StyleReferenceUploadResponse {
  referenceId: string;
  label: string | null;
  filename: string;
  contentType: string;
  width: number;
  height: number;
  fingerprintSummary: FingerprintSummary;
  artifacts: {
    edgeMapAvailable: boolean;
  };
}

export interface StyleMetadata {
  patchId: string;
  matchedFeatureIds: string[];
  geometrySimilarity: number;
  patchSimilarity: number;
  contourRefinement: number;
  preRenderScore: number;
  verificationStatus: "pending" | "verified" | "partial" | "failed";
  clipSimilarity: number | null;
  lpipsDistance: number | null;
  edgeSimilarity: number | null;
  finalStyleScore: number | null;
}

export interface StyleRankedViewpoint {
  id: string;
  sceneId: string;
  sceneType: string;
  composition: CompositionType;
  camera: CameraPose;
  targets: ViewpointTarget[];
  distanceMetersApprox: number;
  baseScore: number;
  score: number;
  scoreBreakdown: ViewpointScoreBreakdown;
  validation: {
    clearanceMeters: number;
    visibleTargetIds: string[];
  };
  style: StyleMetadata;
}

export interface StyleViewpointSearchRequest {
  center: LatLng;
  radiusMeters: number;
  weights?: AnalysisWeights;
  compositions?: CompositionType[];
  maxViewpoints?: number;
  maxPerScene?: number;
  referenceId: string;
  topPatchCount?: number;
}

export interface StyleViewpointSearchSummary {
  sceneCount: number;
  eligibleSceneCount: number;
  candidatesGenerated: number;
  candidatesRejected: {
    templateIneligible: number;
    noConvergence: number;
    underground: number;
    occluded: number;
    outOfBounds: number;
  };
  patchesScanned: number;
  stylePatchMatches: number;
  styleCandidatesRefined: number;
  returned: number;
}

export interface StyleViewpointSearchResponse {
  request: {
    center: LatLng;
    radiusMeters: number;
    zoomUsed: number;
    weights: AnalysisWeights;
    compositions: CompositionType[];
    maxViewpoints: number;
    maxPerScene: number;
    referenceId: string;
    topPatchCount: number;
  };
  reference: {
    referenceId: string;
    label: string | null;
  };
  summary: StyleViewpointSearchSummary;
  viewpoints: StyleRankedViewpoint[];
  source: string;
  fidelity?: Fidelity;
}

export interface StyleVerificationResult {
  referenceId: string;
  viewpointId: string;
  verificationStatus: "verified" | "partial" | "failed";
  clipSimilarity: number | null;
  lpipsDistance: number | null;
  edgeSimilarity: number | null;
  finalStyleScore: number | null;
  warnings: string[];
}
