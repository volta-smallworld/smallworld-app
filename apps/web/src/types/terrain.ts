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
}
