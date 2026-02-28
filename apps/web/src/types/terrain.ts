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
