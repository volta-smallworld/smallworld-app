# Hour 3 Implementation Plan: Deterministic Viewpoint Computation + Proxy Beauty Scoring

## Summary
Build the first ranked-viewpoint pipeline on top of the existing hour-two terrain analysis stack.

This slice starts from the current `POST /api/v1/terrain/analyze` flow and adds a new additive endpoint that:
- recomputes the hour-two terrain analysis for a location,
- derives eligible composition templates from scene seeds,
- solves deterministic camera poses for each eligible scene/template pair,
- rejects physically invalid poses,
- scores valid poses with fast DEM-only proxy metrics,
- returns a ranked list of camera poses for the web UI.

Hour 3 is complete when a user can select a location, run terrain analysis, request viewpoints for one or more composition families, and see ranked camera markers plus heading vectors in the app.

## Scope

### In scope
- New `POST /api/v1/terrain/viewpoints` endpoint
- Ridgeline fractal-dimension distance heuristic
- Composition templates for `ruleOfThirds`, `goldenRatio`, `leadingLine`, and `symmetry`
- Constrained camera solver in a local tangent-plane coordinate system
- Physical feasibility validation:
  - in-bounds check
  - minimum ground clearance
  - line-of-sight to required anchor features
- Fast proxy beauty scoring from the DEM only:
  - viewshed richness
  - terrain entropy
  - skyline fractal score
  - prospect-refuge
  - depth layering
  - mystery
  - water visibility
- Ranked viewpoint list in the web sidebar
- Map overlays for viewpoint positions and heading rays
- Backend automated tests plus frontend smoke validation

### Out of scope
- Cesium screenshot rendering
- Neural scoring
- CACNet verification
- CMA-ES refinement
- Fibonacci spiral templates
- Style-reference upload or matching
- Persistence or saved viewpoint collections
- Switching the Cesium viewer to true terrain; hour 3 remains marker-and-heading overlays only

## Repo Layout
Add the hour-three code in the existing monorepo structure.

```text
/
  ai/
    plans/
      PLAN.md
      hour-1-foundation-slice.md
      hour-two.md
      hour-three.md
  apps/
    api/
      src/
        smallworld_api/
          models/
            terrain.py
            viewpoints.py
          routes/
            terrain.py
          services/
            analysis.py
            camera_geometry.py
            composition_templates.py
            fractals.py
            visibility.py
            viewpoints.py
      tests/
        test_camera_geometry.py
        test_composition_templates.py
        test_fractals.py
        test_visibility_metrics.py
        test_viewpoints_route.py
    web/
      src/
        app/
          page.tsx
        components/
          cesium-map.tsx
          control-panel.tsx
          viewpoint-list.tsx
        lib/
          api.ts
        types/
          terrain.ts
```

## Important Changes Or Additions To Public APIs/Interfaces/Types

### Environment variables
Keep all existing hour-one and hour-two settings. Add:

- `VIEWPOINT_MAX_RETURNED=12`
- `VIEWPOINT_MAX_PER_SCENE=3`
- `VIEWPOINT_DEFAULT_FOV_DEGREES=55`
- `VIEWPOINT_MIN_CLEARANCE_METERS=2`
- `VIEWPOINT_DEDUP_DISTANCE_METERS=150`
- `VIEWPOINT_DEDUP_HEADING_DEGREES=12`
- `VIEWPOINT_SKYLINE_FD_TARGET=1.3`
- `VIEWPOINT_SKYLINE_FD_SIGMA=0.15`
- `VISIBILITY_RAY_COUNT=90`
- `VISIBILITY_STEPS_PER_RAY=40`
- `RIDGE_FRACTAL_SCALES_METERS=150,300,600,1200`
- `RIDGE_DEFAULT_DISTANCE_MULTIPLIER=2.5`

### Existing API
Keep `POST /api/v1/terrain/analyze` unchanged.

### New backend API
Add `POST /api/v1/terrain/viewpoints`.

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
    "ridges": 0.9,
    "cliffs": 0.8,
    "water": 0.7,
    "relief": 1.0
  },
  "compositions": [
    "ruleOfThirds",
    "goldenRatio",
    "leadingLine",
    "symmetry"
  ],
  "maxViewpoints": 12,
  "maxPerScene": 3
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
    "zoomUsed": 12,
    "weights": {
      "peaks": 1.0,
      "ridges": 0.9,
      "cliffs": 0.8,
      "water": 0.7,
      "relief": 1.0
    },
    "compositions": [
      "ruleOfThirds",
      "goldenRatio",
      "leadingLine",
      "symmetry"
    ],
    "maxViewpoints": 12,
    "maxPerScene": 3
  },
  "summary": {
    "sceneCount": 6,
    "eligibleSceneCount": 4,
    "candidatesGenerated": 28,
    "candidatesRejected": {
      "templateIneligible": 7,
      "noConvergence": 3,
      "underground": 2,
      "occluded": 4,
      "outOfBounds": 0
    },
    "returned": 12
  },
  "viewpoints": [
    {
      "id": "vp-1",
      "sceneId": "scene-2",
      "sceneType": "peak-ridge",
      "composition": "ruleOfThirds",
      "camera": {
        "lat": 39.745812,
        "lng": -104.998164,
        "altitudeMeters": 2412.3,
        "headingDegrees": 113.5,
        "pitchDegrees": -8.4,
        "rollDegrees": 0,
        "fovDegrees": 55
      },
      "targets": [
        {
          "featureId": "peak-1",
          "role": "primary",
          "xNorm": 0.667,
          "yNorm": 0.333
        },
        {
          "featureId": "ridge-1",
          "role": "secondary",
          "xNorm": 0.333,
          "yNorm": 0.667
        }
      ],
      "distanceMetersApprox": 1680,
      "score": 0.82,
      "scoreBreakdown": {
        "viewshedRichness": 0.81,
        "terrainEntropy": 0.63,
        "skylineFractal": 0.74,
        "prospectRefuge": 0.69,
        "depthLayering": 0.58,
        "mystery": 0.41,
        "waterVisibility": 0.0
      },
      "validation": {
        "clearanceMeters": 18.4,
        "visibleTargetIds": ["peak-1", "ridge-1"]
      }
    }
  ],
  "source": "aws-terrarium"
}
```

### Validation rules
- `lat` must be between `-90` and `90`
- `lng` must be between `-180` and `180`
- `radiusMeters` must be between `1000` and `50000`
- `weights` follow the existing analysis constraints
- `compositions` may only contain `ruleOfThirds`, `goldenRatio`, `leadingLine`, or `symmetry`
- `maxViewpoints` must be between `1` and `25`
- `maxPerScene` must be between `1` and `5`
- Return `200` with `viewpoints: []` if no scene can produce a valid pose
- Return `422` for oversized tile coverage, invalid enum values, or invalid limits
- Viewpoints must be sorted by `score` descending
- Ties must break by scene score descending, then by viewpoint id ascending

### Frontend TypeScript types
Add:

- `CompositionType = "ruleOfThirds" | "goldenRatio" | "leadingLine" | "symmetry"`
- `ViewpointSearchRequest`
- `ViewpointSearchResponse`
- `CameraPose`
- `ViewpointTarget`
- `ViewpointScoreBreakdown`
- `RankedViewpoint`
- `ViewpointSearchSummary`
- `ViewpointFetchState = "idle" | "loading" | "success" | "error"`

Extend:

- `AnalysisOverlayKey` with `"viewpoints"`
- page state with `selectedViewpointId: string | null`

## Composition Templates And Defaults

### Shared conventions
- Use normalized screen coordinates where `(0, 0)` is top-left and `(1, 1)` is bottom-right
- Use fixed horizontal FOV `55°` for all hour-three candidates
- Set `rollDegrees = 0` for every candidate
- Compute pitch from horizon ratio before pose solving
- Use local ENU coordinates centered on each scene center for all camera math

### Rule of thirds
- Eligible scenes: `peak-ridge`, `peak-water`, `cliff-water`, `multi-peak`, `mixed-terrain`
- Primary anchor: top-scoring point feature in the scene, preferring peak over cliff
- Secondary anchor: top-scoring line feature midpoint, else the next-highest point feature
- Variants:
  - `primary=(0.667, 0.333)`, `secondary=(0.333, 0.667)`
  - `primary=(0.333, 0.333)`, `secondary=(0.667, 0.667)`
- Horizon ratio: `0.333`

### Golden ratio
- Eligible scenes: same as rule of thirds
- Primary anchor: same rule as above
- Secondary anchor: same rule as above
- Variants:
  - `primary=(0.618, 0.382)`, `secondary=(0.382, 0.618)`
  - `primary=(0.382, 0.382)`, `secondary=(0.618, 0.618)`
- Horizon ratio: `0.382`

### Leading line
- Eligible scenes: any scene with at least one ridge or water channel and one point feature
- Line anchor: highest-scoring ridge, else highest-scoring water channel
- Subject anchor: highest-scoring point feature
- Entry corner rule:
  - use bottom-left entry if the line start is west of its end in local ENU
  - use bottom-right entry otherwise
- Subject target: `(0.618, 0.382)`
- Horizon ratio: `0.45`
- Solver type: constructive placement, not least-squares PnP

### Symmetry
- Eligible scenes: scenes containing at least two peaks or at least two cliffs
- Anchor pair:
  - first choice: top two peaks
  - second choice: top two cliffs
- Targets:
  - left anchor `(0.35, 0.5)`
  - right anchor `(0.65, 0.5)`
- Horizon ratio: `0.5`

## Implementation Sequence

### 1. Add viewpoint models
Create `models/viewpoints.py` and keep the route contract out of `terrain.py`.

Add Pydantic models for:
- request echo
- composition enum
- camera pose
- viewpoint target
- score breakdown
- validation summary
- ranked viewpoint
- route summary block
- top-level response

### 2. Add geometry primitives
Create `services/camera_geometry.py`.

Implement:
- lat/lng to local ENU meters around a scene center
- ENU back to lat/lng
- bilinear DEM elevation sampling at fractional row and column
- heading and pitch helpers
- normalized pinhole projection from 3D point to `(xNorm, yNorm)`
- pitch-from-horizon helper:
  - `pitch = atan((horizonRatio - 0.5) * 2 * tan(verticalFov / 2))`
- DEM line-of-sight ray marcher:
  - sample 64 points between camera and target
  - fail if any terrain sample exceeds the segment height minus `0.5m`

### 3. Add fractal-distance utilities
Create `services/fractals.py`.

Implement:
- 1D box-counting fractal dimension for sampled profiles
- Gaussian score centered at `D=1.3` with `sigma=0.15`
- ridge-profile smoothing over `150m`, `300m`, `600m`, `1200m`
- preferred viewing distance:
  - sample ridge elevations from path vertices
  - compute FD at each smoothing scale
  - choose the scale whose FD is closest to `1.3`
  - convert scale to distance with:
    - `distance = scaleMeters / tan(fovRadians / 2)`
- if the scene has no ridge, use:
  - `distance = max(scene_extent_meters * 2.5, 400)`

### 4. Add composition template definitions
Create `services/composition_templates.py`.

Implement a static template registry where each template includes:
- template name
- eligible scene rule
- target coordinate variants
- horizon ratio
- required anchor roles
- solver type:
  - `pnp`
  - `leading_line`

The registry must be deterministic and not data-driven for hour three.

### 5. Build scene anchor selection
Create `services/viewpoints.py` with an internal `SceneContext`.

For every scene:
- build a feature index from `scene.featureIds`
- derive:
  - `primaryPoint`
  - `secondaryPoint`
  - `primaryLine`
  - `symmetryPair`
  - `sceneExtentMeters`
  - `sceneReliefMeters`
- use the same feature ordering every time:
  - score descending
  - id ascending as tie-breaker

### 6. Solve camera poses
Use two solver paths.

For `ruleOfThirds`, `goldenRatio`, and `symmetry`:
- solve over unknowns `[camX, camY, camZ, yaw]`
- keep pitch fixed from the template horizon ratio
- use `scipy.optimize.least_squares`
- objective:
  - project each required 3D anchor into normalized image coordinates
  - compute residual against template targets
- initial guess:
  - camera origin on the opposite side of the scene from the primary anchor
  - distance from ridge fractal heuristic or scene extent fallback
  - altitude = `max(anchor elevations) + max(30, sceneReliefMeters * 0.15)`
  - yaw aimed at the midpoint of all required anchors
- accept only if:
  - solver converges
  - final residual RMS `< 0.08`
  - camera is within request bounds
  - ground clearance `>= 2m`
  - every required target passes line-of-sight

For `leadingLine`:
- place the camera behind the first third of the chosen line
- offset backward along the negative line tangent by the preferred viewing distance
- set yaw toward the subject anchor
- set pitch from the template horizon ratio
- set altitude to `groundElevation + max(10, sceneReliefMeters * 0.08)`
- run the same physical validation as above

### 7. Deduplicate candidates
Deduplicate after validation and before scoring.

Two candidates are duplicates if all are true:
- same `sceneId`
- same `composition`
- camera separation `< 150m`
- heading delta `< 12°`

Keep the higher-score candidate only.

### 8. Add visibility and proxy beauty scoring
Create `services/visibility.py`.

For each candidate:
- ray-cast `90` azimuth rays over the camera FOV
- sample `40` distance steps per ray out to the request radius
- treat a cell as visible if its elevation angle is greater than the current max for that ray

Compute component scores in `[0, 1]`:

- `viewshedRichness`
  - visible interest sum divided by total interest sum
  - weight `0.20`
- `terrainEntropy`
  - normalized Shannon entropy of visible elevation bins
  - use `8` bins
  - weight `0.15`
- `skylineFractal`
  - skyline profile from max elevation angle per ray
  - 1D box-counting FD score against target `1.3`
  - weight `0.20`
- `prospectRefuge`
  - prospect = visible-area fraction
  - refuge = nearby terrain-above-horizon fraction within `500m`
  - score = harmonic mean
  - weight `0.15`
- `depthLayering`
  - split visible cells into near, mid, far by thirds of distance
  - score = normalized entropy of visible-interest mass across the three bands
  - weight `0.10`
- `mystery`
  - ratio of high-interest cells immediately behind first occluders to all visible high-interest cells
  - weight `0.10`
- `waterVisibility`
  - visible water path points divided by total water path points
  - weight `0.10`

Set total score to the weighted sum of the seven component scores.

### 9. Expose the route
Add `POST /api/v1/terrain/viewpoints` in `routes/terrain.py`.

The route must:
- reuse the existing DEM snapshot fetch
- recompute the hour-two derivatives, features, hotspots, and scenes internally
- call the new viewpoint orchestration service
- return:
  - request echo
  - rejection summary
  - ranked viewpoints
  - source string
- never require the client to send prior analysis output back to the API

### 10. Wire the web app
Keep the current analysis flow and add a second explicit step.

Frontend changes:
- add composition toggle chips to `control-panel.tsx`
- add a second button: `Find Viewpoints`
- enable `Find Viewpoints` only when terrain analysis has succeeded for the current map selection and weights
- maintain separate state for:
  - `viewpointFetchState`
  - `viewpointError`
  - `viewpointResult`
  - `selectedViewpointId`

Add `viewpoint-list.tsx`:
- list viewpoints in descending score order
- show:
  - composition
  - scene type
  - score
  - lat/lng
  - altitude
  - heading
  - pitch
  - top three score components
- clicking a row sets `selectedViewpointId`

Update `cesium-map.tsx`:
- add a `"viewpoints"` overlay toggle
- render each viewpoint as a magenta point
- render a short heading ray of `300m` projected in the heading direction
- render the selected viewpoint with a larger white outline
- on selection, recentre the map on the viewpoint marker only; do not attempt cinematic camera preview in hour three

Update `lib/api.ts`:
- add `findViewpoints()`

## Test Cases And Scenarios

### Backend unit tests
- `test_camera_geometry.py`
  - ENU round-trip stays within `2m`
  - projection math returns expected normalized coordinates for a synthetic camera
  - pitch-from-horizon returns the expected sign and magnitude
  - line-of-sight fails when a blocking ridge is inserted between camera and target

- `test_fractals.py`
  - box-counting FD is stable on a straight line profile
  - a noisier profile scores closer to the `1.3` target than a flat profile
  - preferred distance picks the scale whose FD is nearest the target

- `test_composition_templates.py`
  - scene eligibility rules accept and reject the correct scene shapes
  - anchor-role selection is deterministic
  - symmetry is skipped unless a valid point pair exists

- `test_visibility_metrics.py`
  - each score component stays within `[0, 1]`
  - visible-area changes affect `viewshedRichness` and `prospectRefuge` in the expected direction
  - skyline FD score increases when the skyline profile becomes more varied
  - `waterVisibility` is zero when no water points are visible

### Backend route tests
- `test_viewpoints_route.py`
  - a valid request returns `200` with sorted viewpoints
  - composition filtering returns only the requested composition families
  - `maxViewpoints` and `maxPerScene` are enforced
  - if all candidates fail validation, the route returns `200` with `viewpoints: []`
  - invalid composition names return `422`

### Frontend smoke scenarios
- composition chips update request payloads
- `Find Viewpoints` stays disabled until terrain analysis succeeds
- successful viewpoint response renders list rows and map markers
- selecting a viewpoint highlights the matching marker
- viewpoint loading and error states do not overwrite terrain analysis state

## Acceptance Criteria
- A user can analyze a mountainous area and request viewpoints without leaving the main page
- The API returns ranked camera poses with coordinates, altitude, heading, pitch, composition type, and score breakdown
- Every returned viewpoint satisfies:
  - in bounds
  - clearance `>= 2m`
  - line-of-sight to all required anchors
  - score in `[0, 1]`
- The frontend can display at least `12` viewpoints, highlight one, and show its map position plus heading
- Rendering, neural scoring, and CMA-ES are not required for this slice

## Assumptions And Defaults
- The current hour-two pipeline in `POST /api/v1/terrain/analyze` is the source of truth for scenes and features
- The existing `128 x 128` DEM grid is sufficient for hour-three heuristics even though it is too coarse for production-grade camera placement
- Cesium remains an overlay map in hour three; photorealistic viewpoint preview is intentionally deferred to hour four
- Only four composition families ship in hour three: `ruleOfThirds`, `goldenRatio`, `leadingLine`, `symmetry`
- Water means water channels only; lake-specific reflection logic stays out of scope until later
- Proxy beauty scores are heuristic ranking signals, not user-facing claims of objective image quality
