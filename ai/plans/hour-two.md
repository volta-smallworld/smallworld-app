# Hour 2 Implementation Plan: Terrain Analysis Slice

## Summary
Build on the hour-one elevation grid pipeline and ship the first terrain-analysis loop:

1. Reuse the existing Terrarium fetch/decode path as the analysis input.
2. Compute terrain derivatives from the fixed-size DEM grid.
3. Extract sparse terrain features: peaks, ridgelines, cliffs, and water channels.
4. Combine those signals into a weighted interest map and lightweight scene groups.
5. Expose the results through an additive API and render simple overlays in the web UI.

This hour-two slice is complete when a user can select an area, run terrain analysis, tune feature weights, and see detected features plus grouped scenes in the app.

## Scope

### In scope
- Keep the current hour-one `POST /api/v1/terrain/elevation-grid` contract working
- Add a new terrain analysis endpoint on top of the existing DEM pipeline
- Terrain derivatives using the fixed `128 x 128` grid
- Heuristic feature extraction for peaks, ridgelines, cliffs, and water channels
- Weighted interest map computation with user-adjustable weights
- Simple scene grouping from nearby compatible features
- Frontend controls for analysis weights and overlay visibility
- Minimal automated backend tests plus frontend smoke validation

### Out of scope
- Deterministic camera pose solving
- Beauty scoring beyond the weighted interest map
- Headless rendering, neural scoring, or CMA-ES refinement
- Style reference upload or structural matching
- Persistence, saved scenes, auth, or sharing
- GIS-grade hydrology or landform classification
- Lakes, saddles, or geomorphons unless they fall out nearly for free

## Repo Layout
Extend the hour-one monorepo without changing the overall structure.

```text
/
  ai/
    plans/
      hour-one.md
      hour-two.md
  apps/
    api/
      pyproject.toml
      src/
        smallworld_api/
          models/
            terrain.py
          routes/
            terrain.py
          services/
            terrarium.py
            analysis.py
            derivatives.py
            features.py
            scenes.py
            tiles.py
      tests/
        test_derivatives.py
        test_feature_extraction.py
        test_scene_grouping.py
        test_terrain_analysis_route.py
    web/
      src/
        app/
          page.tsx
        components/
          cesium-map.tsx
          control-panel.tsx
          terrain-result-panel.tsx
          scene-list.tsx
        lib/
          api.ts
        types/
          terrain.ts
```

## Important Changes Or Additions To Public APIs/Interfaces/Types

### Environment variables
Keep hour-one env vars and add optional analysis defaults:

- API:
  - `PEAK_MIN_PROMINENCE_METERS=120`
  - `FLOW_ACCUMULATION_THRESHOLD=150`
  - `CLIFF_CURVATURE_PERCENTILE=95`
  - `SCENE_CLUSTER_RADIUS_METERS=5000`
  - `MAX_SCENES_RETURNED=20`

### Backend API
Keep the existing endpoint unchanged:

- `POST /api/v1/terrain/elevation-grid`

Add:

- `POST /api/v1/terrain/analyze`

Request body:

```json
{
  "center": {
    "lat": 39.7392,
    "lng": -104.9903
  },
  "radiusMeters": 5000,
  "weights": {
    "peaks": 1.0,
    "ridges": 0.8,
    "cliffs": 0.8,
    "water": 0.6,
    "relief": 1.0
  }
}
```

Response body:

```json
{
  "request": {
    "center": {
      "lat": 39.7392,
      "lng": -104.9903
    },
    "radiusMeters": 5000,
    "zoomUsed": 12
  },
  "bounds": {
    "north": 39.7841,
    "south": 39.6943,
    "east": -104.9321,
    "west": -105.0485
  },
  "grid": {
    "width": 128,
    "height": 128,
    "cellSizeMetersApprox": 78.1
  },
  "layers": {
    "slopeDegrees": {
      "min": 0.0,
      "max": 41.7,
      "values": [[4.1, 4.2]]
    },
    "profileCurvature": {
      "min": -2.3,
      "max": 3.7,
      "values": [[0.1, 0.2]]
    },
    "relief": {
      "min": 2.0,
      "max": 884.6,
      "values": [[33.0, 35.1]]
    },
    "interest": {
      "min": 0.0,
      "max": 1.0,
      "values": [[0.22, 0.24]]
    }
  },
  "features": {
    "peaks": [
      {
        "id": "peak-1",
        "lat": 39.751,
        "lng": -104.981,
        "elevation": 2401.2,
        "score": 0.93
      }
    ],
    "ridgelines": [
      {
        "id": "ridge-1",
        "coordinates": [
          [-104.99, 39.75],
          [-104.98, 39.76]
        ],
        "score": 0.81
      }
    ],
    "cliffs": [
      {
        "id": "cliff-1",
        "lat": 39.742,
        "lng": -104.996,
        "score": 0.78
      }
    ],
    "water": [
      {
        "id": "water-1",
        "coordinates": [
          [-104.995, 39.741],
          [-104.992, 39.738]
        ],
        "score": 0.74
      }
    ]
  },
  "scenes": [
    {
      "id": "scene-1",
      "type": "peak-ridge",
      "featureIds": ["peak-1", "ridge-1"],
      "score": 0.88
    }
  ],
  "source": "aws-terrarium"
}
```

### Validation rules
- `lat` must be between `-90` and `90`
- `lng` must be between `-180` and `180`
- `radiusMeters` must be between `1000` and `50000`
- Each weight must be between `0` and `3`
- Return `200` with empty feature arrays if an area is valid but no features survive filtering
- Cap returned scenes to `MAX_SCENES_RETURNED`
- If the tile coverage exceeds `MAX_TILES_PER_REQUEST`, return `422` with a clear message

### Frontend TypeScript types
Extend the web-local terrain types with:

- `TerrainAnalysisRequest`
- `TerrainAnalysisResponse`
- `AnalysisWeights`
- `RasterLayer`
- `PointFeature`
- `LineFeature`
- `SceneGroup`
- `AnalysisOverlayKey = "peaks" | "ridges" | "cliffs" | "water" | "interest"`

## Implementation Sequence

### 1. Refactor the backend terrain pipeline for reuse
- Keep `get_elevation_grid()` intact for the hour-one route
- Extract a shared lower-level function that returns:
  - analysis grid
  - geographic bounds
  - tile metadata
  - approximate cell size
- Put the hour-two orchestration in `services/analysis.py` so route code stays thin

### 2. Add derivative computation utilities
- Update `apps/api/pyproject.toml` to add `scipy` if needed for neighborhood filters and connected components
- In `derivatives.py`, implement:
  - slope in degrees from DEM gradients
  - profile curvature
  - plan curvature or Laplacian-style ruggedness proxy
  - local relief using a small moving window
  - normalization helpers for layer blending
- Keep the math deterministic and testable on synthetic arrays

### 3. Extract the first terrain features
- In `features.py`, implement:
  - peaks via local maxima plus minimum prominence filtering
  - ridgelines via inverted-surface flow accumulation and line tracing
  - water channels via flow accumulation on the original DEM
  - cliffs via high profile-curvature cells gated by slope threshold
- Return sparse feature objects, not every candidate cell
- Prefer simple heuristics over heavy GIS machinery so the slice stays achievable in one hour

### 4. Compute the interest map and group scenes
- Build a weighted `interest` raster from normalized feature-distance and derivative layers
- Default blend:
  - `peaks`
  - `ridges`
  - `cliffs`
  - `water`
  - `relief`
- In `scenes.py`, cluster nearby compatible features using a simple distance threshold
- Derive lightweight scene labels from feature combinations:
  - `peak-ridge`
  - `peak-water`
  - `cliff-valley`
  - `multi-peak`
- Score scenes by combined feature strength plus local interest density

### 5. Expose an additive analysis route
- Extend `models/terrain.py` with analysis request/response models
- Add `POST /api/v1/terrain/analyze` in `routes/terrain.py`
- Reuse the same error translation pattern as hour one:
  - `422` for invalid requests or oversized tile coverage
  - `502` for upstream Terrarium fetch failures
- Keep the hour-one endpoint stable so the app can fall back if needed

### 6. Add the hour-two web controls and results
- Extend the existing control panel with:
  - analysis weight sliders
  - a primary `Analyze Terrain` action
  - overlay toggles for peaks, ridges, cliffs, water, and interest hotspots
- Update `lib/api.ts` to call the new analysis endpoint
- Update the result panel to show:
  - feature counts by kind
  - top peaks and top scenes
  - interest and slope summary ranges
- In `cesium-map.tsx`, render:
  - peak and cliff markers
  - ridge and water polylines
  - optional top-interest hotspot markers instead of a full raster heatmap

### 7. Document and validate the slice
- Update the root `README.md` with the new analysis endpoint and example payload
- Add manual validation notes for overlay toggles and weight changes
- Make sure another engineer can still run the stack locally without extra guesswork

## Test Cases And Scenarios

### Backend automated tests
- `test_derivatives.py`
  - plane surface produces near-constant slope
  - synthetic ridge or bowl produces expected curvature sign patterns
  - local relief window returns expected values
- `test_feature_extraction.py`
  - isolated synthetic summit is detected as a peak
  - step edge produces cliff candidates
  - simple ridge surface yields a traced ridgeline
  - simple valley surface yields a water channel
- `test_scene_grouping.py`
  - nearby compatible features form deterministic scene groups
  - distant features do not merge into one scene
- `test_terrain_analysis_route.py`
  - valid request returns `200`
  - response includes `layers`, `features`, and `scenes`
  - invalid weights return `422`
  - empty-feature case still returns `200`
  - hour-one `elevation-grid` route still returns its original shape

### Frontend validation
Use lightweight checks again instead of a full browser suite.

- Existing map selection UX still works
- Clicking `Analyze Terrain` calls the new endpoint and renders results
- Changing weights changes the request payload and the returned rankings
- Overlay toggles add and remove Cesium entities correctly
- Failure states remain visible and understandable
- The app still works on a fresh local start with the same web and API commands

## Acceptance Criteria
- The existing hour-one terrain endpoint still works unchanged
- A new analysis endpoint returns derivatives, sparse features, and grouped scenes for the same selected area
- Users can adjust analysis weights from the UI and rerun analysis
- Peaks, ridges, cliffs, and water candidates are visible in the map or result panel
- Scene groups are returned and summarized in a way that can feed hour three
- Backend tests cover the derivative and feature math with deterministic synthetic cases
- The repo docs explain how to run and exercise the new terrain-analysis flow locally

## Assumptions And Defaults
- Hour one is already implemented and remains the foundation
- Terrain analysis still uses AWS Terrarium tiles at fixed zoom `12`
- The analysis grid remains `128 x 128` for speed and predictable payload size
- Feature extraction is heuristic and fast, not survey-grade GIS
- Scene grouping is rule-based and proximity-driven, not learned
- The UI uses sparse vector overlays and hotspot markers, not a full raster heatmap on the globe
- One synchronous request per analysis is acceptable for the hour-two slice
- Camera solving, ranking, and rendering begin in hour three, not here
