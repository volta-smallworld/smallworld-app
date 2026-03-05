# Smallworld AI Pipeline Reference

> **Living document.** Update this file whenever a pipeline stage, service, API endpoint, MCP tool, or data flow is added, modified, or removed. This is the single source of truth for understanding how the AI pipeline works end-to-end.

Last updated: 2026-03-01

---

## Pipeline Overview

The Smallworld AI pipeline transforms a geographic point into ranked, rendered landscape photography previews. It runs in stages, each building on the previous:

```
Location (lat/lng/radius)
  -> Terrain Acquisition (Terrarium tiles -> DEM grid)
    -> Terrain Analysis (features, hotspots, scenes)
      -> Viewpoint Generation (camera poses)
        -> [Optional] Style Matching (reference image -> style-aware poses)
          -> Camera Safety (AGL enforcement)
            -> Preview Rendering (Cesium headless -> PNG)
              -> Enhancement (Gemini image model)
                -> Composition Verification
```

---

## Stage 1: Terrain Acquisition

**Purpose:** Fetch elevation data for a geographic area and produce a 128x128 DEM grid.

| Component | File | Function |
|---|---|---|
| Tile math | `services/tiles.py` | `center_radius_to_bounds()`, `bounds_to_tile_range()`, `tile_bounds()` |
| Tile fetch + decode | `services/terrarium.py` | `fetch_tile()`, `decode_terrarium()`, `fetch_and_stitch()` |
| Crop + resample | `services/terrarium.py` | `crop_and_resample()` → always 128x128 |
| DEM snapshot | `services/terrarium.py` | `fetch_dem_snapshot()` — single entry point |

**Data source:** AWS Terrarium tiles (`R*256 + G + B/256 - 32768`)
**Tile size:** 256x256 per tile
**Output grid:** 128x128 (hardcoded `GRID_SIZE`)
**Tile cap:** 36 tiles max per request (auto-reduces zoom if exceeded)
**Default zoom:** 12

### Precise Point Elevation (added 2026-03-01)

Separate from the 128x128 grid pipeline. Fetches 1-4 raw tiles for bilinear interpolation at a single point.

| Component | File | Function |
|---|---|---|
| Fractional tile coords | `services/tiles.py` | `_lat_to_tile_y_frac()`, `_lng_to_tile_x_frac()` |
| Point sampler | `services/terrarium.py` | `sample_point_elevation()` |

**Default zoom:** 14 (~10m/pixel), configurable via `POINT_ELEVATION_DEFAULT_ZOOM`
**Output:** `PointElevationResult` with elevation, tile coords, meters per pixel

---

## Stage 2: Terrain Analysis

**Purpose:** Compute terrain derivatives and extract geographic features from the DEM.

| Component | File | Function |
|---|---|---|
| Slope | `services/derivatives.py` | `compute_slope_degrees()` |
| Curvature | `services/derivatives.py` | `compute_profile_curvature()` |
| Local relief | `services/derivatives.py` | `compute_local_relief()` |
| Peaks | `services/features.py` | `extract_peaks()` |
| Ridges | `services/features.py` | `extract_ridges()` |
| Cliffs | `services/features.py` | `extract_cliffs()` |
| Water channels | `services/features.py` | `extract_water_channels()` |
| Interest raster | `services/analysis.py` | `build_interest_raster()` |
| Hotspots | `services/analysis.py` | `extract_hotspots()` |
| Scenes | `services/scenes.py` | `group_scenes()` |

**Weights** (configurable per request): peaks (1.0), ridges (0.9), cliffs (0.8), water (0.7), relief (1.0)

---

## Stage 3: Viewpoint Generation

**Purpose:** Generate ranked camera poses for discovered scenes.

| Component | File | Function |
|---|---|---|
| Viewpoint solver | `services/viewpoints.py` | `generate_viewpoints()` |
| Camera geometry | `services/camera_geometry.py` | `bilinear_elevation()`, `compute_heading()`, `pitch_from_horizon_ratio()`, `project_to_image()`, `check_line_of_sight()` |
| Composition templates | `services/composition_templates.py` | Template-specific placement rules |
| Visibility | `services/visibility.py` | Viewshed analysis |

**Scoring factors:** viewshed richness, terrain entropy, skyline fractal dimension, prospect-refuge, depth layering, mystery, water visibility

**Compositions:** `rule_of_thirds`, `golden_ratio`, `leading_line`, `symmetry`

---

## Stage 4: Style Matching (optional)

**Purpose:** Match DEM patches to an uploaded reference image and refine camera poses for visual similarity.

| Component | File | Function |
|---|---|---|
| Patch extraction | `services/style_matching.py` | `_extract_dem_patches()` |
| Contour fingerprint | `services/style_fingerprint.py` | `extract_fingerprint_from_contours()` |
| Candidate refinement | `services/style_matching.py` | `_refine_style_candidate()` |
| Orchestrator | `services/style_matching.py` | `find_style_viewpoints()` |

**Score formula:** `0.45 * contour_refinement + 0.35 * patch_similarity + 0.20 * base_score`

---

## Stage 5: Camera Safety (AGL Enforcement)

**Purpose:** Prevent camera-inside-terrain failures by enforcing a minimum Above Ground Level (AGL) clearance.

Three independent defense layers, each using a different terrain source:

| Layer | Location | Method | Terrain Source | I/O |
|---|---|---|---|---|
| Post-refinement | `services/style_matching.py` | `enforce_agl_floor_dem()` | 128x128 DEM grid | Sync, none |
| Pre-render | `services/previews.py` | `enforce_agl_floor_precise()` | Raw Terrarium tiles (zoom 14) | Async, 1-4 tiles |
| Renderer-side | `render-preview-inner.tsx` | `sampleTerrainMostDetailed` / `sampleHeightMostDetailed` | Cesium World Terrain or Google 3D Tiles | Async, renderer-internal |

| Component | File | Function |
|---|---|---|
| DEM-based clamp | `services/camera_safety.py` | `enforce_agl_floor_dem()` |
| Precise clamp | `services/camera_safety.py` | `enforce_agl_floor_precise()` |
| Renderer clamp | `render-preview-inner.tsx` | Inline in tile-ready callback |

**Config:**
- `CAMERA_AGL_FLOOR_METERS` — minimum clearance (default: 5.0m)
- `RENDERER_TERRAIN_CLAMP_ENABLED` — enable renderer-side clamp (default: true)
- `RENDERER_TERRAIN_SAMPLE_TIMEOUT_MS` — renderer sample timeout (default: 3000ms)

**Warning codes emitted:**
- `camera_clamped_above_terrain` — pre-render clamp applied
- `terrain_sample_unavailable` — pre-render sample failed
- `renderer_terrain_clamp_applied` — renderer clamp applied
- `renderer_terrain_sample_failed` — renderer sample failed

---

## Stage 6: Preview Rendering

**Purpose:** Produce a PNG image from a camera pose using headless Cesium.

| Component | File | Function |
|---|---|---|
| Pipeline orchestrator | `services/previews.py` | `render_preview_pipeline()` |
| Renderer launcher | `services/preview_renderer.py` | `render_preview()` |
| Render client | `render-preview-inner.tsx` | React component with Cesium viewer |
| Puppeteer script | `scripts/render-preview.mjs` | Node.js subprocess |
| Artifact storage | `services/preview_artifacts.py` | ID generation, save, cleanup |

**Render flow:**
1. Encode camera/viewport/safety as base64url JSON payload
2. Launch Puppeteer subprocess pointing at Next.js render route
3. Cesium viewer loads, sets camera, waits for tiles
4. (If safety enabled) Sample terrain at camera position, clamp if needed
5. Compute anchor projections
6. Signal ready via `window.__SMALLWORLD_RENDER_READY__`
7. Puppeteer screenshots and exits
8. Python reads image + `__SMALLWORLD_FRAME_STATE__` from stdout

**Fallback:** If Google 3D Tiles render fails, retries without Google 3D.

**Viewport:** default 1536x1024

---

## Stage 7: Enhancement (optional)

**Purpose:** Apply AI-powered visual enhancement to the raw render.

| Component | File | Function |
|---|---|---|
| Enhancement | `services/preview_enhancement.py` | `enhance_preview()` |
| Prompt builder | `services/preview_enhancement.py` | `build_enhancement_prompt()` |

**Model:** Gemini (configurable, default `gemini-3.1-flash-image-preview`)
**Requires:** `GEMINI_API_KEY` env var

---

## Stage 8: Composition Verification

**Purpose:** Verify that the rendered image matches the intended composition template.

| Component | File | Function |
|---|---|---|
| Verifier | `services/composition_verifier.py` | `verify_composition()` |

---

## Point Context Service

**Purpose:** Combine precise ground elevation with local terrain analysis for a single point. Used for camera safety checks and terrain queries.

| Component | File | Function |
|---|---|---|
| Point context | `services/point_context.py` | `get_point_context()` |

**Combines:**
1. `sample_point_elevation()` for precise ground elevation
2. `fetch_dem_snapshot()` for local area DEM
3. Terrain derivatives (slope, curvature, relief) at the point
4. Optional camera AGL computation

---

## API Endpoints

| Method | Path | Purpose | ADR |
|---|---|---|---|
| GET | `/healthz` | Health check | — |
| POST | `/api/v1/terrain/elevation-grid` | 128x128 DEM grid | [0007](../adr/0007-standardize-the-hour-one-elevation-grid-contract.md) |
| POST | `/api/v1/terrain/analyze` | Terrain analysis with features, hotspots, scenes | — |
| POST | `/api/v1/terrain/viewpoints` | Viewpoint generation | — |
| POST | `/api/v1/terrain/point-context` | Precise ground elevation + local terrain context | [0009](../adr/0009-precise-point-elevation-and-agl-camera-safety.md) |
| POST | `/api/v1/previews/render` | Preview rendering pipeline | [0008](../adr/0008-hour-four-preview-architecture.md) |
| GET | `/api/v1/previews/{id}/artifacts/{type}` | Serve preview artifacts | [0008](../adr/0008-hour-four-preview-architecture.md) |

---

## MCP Tools

| Tool | Purpose | Input | Added |
|---|---|---|---|
| `terrain_analyze_area` | Terrain analysis around a point | lat, lng, radius, zoom, include_elevations | v1.0 |
| `terrain_find_viewpoints` | Discover ranked camera poses | lat, lng, radius, weights, compositions, limits | v1.1 |
| `preview_render_pose` | Render a preview image | camera, scene, composition, viewport, enhancement | v1.1 |
| `terrain_point_context` | Precise ground elevation + AGL check | lat, lng, camera_altitude, context_radius, zoom | v1.2 |

**MCP Resources:**
- `smallworld://server-info` — server capabilities and configuration
- `smallworld://usage-guidance` — agent workflow guidance

---

## Configuration Reference

### Terrain
| Setting | Default | Description |
|---|---|---|
| `DEFAULT_TERRARIUM_ZOOM` | 12 | Default zoom for DEM grid |
| `MAX_TILES_PER_REQUEST` | 36 | Tile cap per request |
| `POINT_ELEVATION_DEFAULT_ZOOM` | 14 | Zoom for precise point sampling |

### Camera Safety
| Setting | Default | Description |
|---|---|---|
| `CAMERA_AGL_FLOOR_METERS` | 5.0 | Minimum AGL clearance |
| `RENDERER_TERRAIN_CLAMP_ENABLED` | true | Enable renderer-side clamp |
| `RENDERER_TERRAIN_SAMPLE_TIMEOUT_MS` | 3000 | Renderer sample timeout |

### Preview Rendering
| Setting | Default | Description |
|---|---|---|
| `PREVIEW_RENDERER_BASE_URL` | `http://127.0.0.1:3000/render/preview` | Renderer URL |
| `PREVIEW_RENDER_TIMEOUT_SECONDS` | 30 | Render subprocess timeout |
| `PREVIEW_DEFAULT_WIDTH` | 1536 | Default viewport width |
| `PREVIEW_DEFAULT_HEIGHT` | 1024 | Default viewport height |
| `PREVIEW_DEFAULT_FOV_DEG` | 50.0 | Default field of view |

### External Providers
| Setting | Default | Description |
|---|---|---|
| `CESIUM_ION_TOKEN` | (empty) | Cesium Ion access token |
| `MAPBOX_ACCESS_TOKEN` | (empty) | Mapbox satellite imagery |
| `GOOGLE_MAPS_API_KEY` | (empty) | Google 3D Tiles |
| `GEMINI_API_KEY` | (empty) | Gemini enhancement model |

---

## Data Flow Diagram

```
                              ┌─────────────────────┐
                              │  Geographic Input    │
                              │  (lat, lng, radius)  │
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  AWS Terrarium Tiles │
                              │  (zoom 12, 256x256)  │
                              └──────────┬──────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                     │
         ┌──────────▼──────────┐  ┌─────▼─────┐   ┌─────────▼─────────┐
         │  128x128 DEM Grid   │  │  Analysis  │   │  Point Sampler    │
         │  (crop + resample)  │  │  Pipeline  │   │  (zoom 14, raw)   │
         └──────────┬──────────┘  └─────┬─────┘   └─────────┬─────────┘
                    │                    │                     │
                    │           ┌────────▼────────┐           │
                    │           │   Features,     │           │
                    │           │   Hotspots,     │           │
                    │           │   Scenes        │           │
                    │           └────────┬────────┘           │
                    │                    │                     │
                    │           ┌────────▼────────┐           │
                    │           │   Viewpoint     │           │
                    │           │   Generation    │           │
                    │           └────────┬────────┘           │
                    │                    │                     │
                    │  ┌─────────────────┼──────────────┐     │
                    │  │                 │              │     │
                    │  │    ┌────────────▼───────────┐  │     │
                    │  │    │  AGL Safety Layer 1    │  │     │
                    │  │    │  (DEM-based, sync)     │◄─┘     │
                    │  │    └────────────┬───────────┘        │
                    │  │                 │                     │
                    │  │    ┌────────────▼───────────┐        │
                    │  │    │  AGL Safety Layer 2    │◄───────┘
                    │  │    │  (precise tiles, async)│
                    │  │    └────────────┬───────────┘
                    │  │                 │
                    │  │    ┌────────────▼───────────┐
                    │  │    │  Cesium Headless Render │
                    │  │    │  + AGL Safety Layer 3   │
                    │  │    │  (renderer-native)      │
                    │  │    └────────────┬───────────┘
                    │  │                 │
                    │  │    ┌────────────▼───────────┐
                    │  │    │  Enhancement (Gemini)  │
                    │  │    └────────────┬───────────┘
                    │  │                 │
                    │  │    ┌────────────▼───────────┐
                    │  │    │  Composition Verify    │
                    │  │    └────────────┬───────────┘
                    │  │                 │
                    │  │    ┌────────────▼───────────┐
                    │  │    │  Preview Artifact      │
                    │  │    │  (PNG + metadata)      │
                    │  │    └────────────────────────┘
                    │  │
```

---

## Future Roadmap

- **DEM upgrade: Terrarium → Copernicus GLO-30** — ~4x vertical accuracy improvement (4m RMSE vs 16m). Free COG tiles on AWS S3. Requires adding `rasterio`/GDAL dependency. See [dem-upgrade-research.md](dem-upgrade-research.md) for full analysis and phased migration plan.

---

## Changelog

| Date | Change | ADR | Files |
|---|---|---|---|
| 2026-02-28 | Initial terrain acquisition + 128x128 grid | [0006](../adr/0006-use-aws-terrarium-tiles-for-hour-one-dem-source.md), [0007](../adr/0007-standardize-the-hour-one-elevation-grid-contract.md) | `terrarium.py`, `tiles.py` |
| 2026-02-28 | Terrain analysis (features, hotspots, scenes) | — | `derivatives.py`, `features.py`, `analysis.py`, `scenes.py` |
| 2026-02-28 | Viewpoint generation | — | `viewpoints.py`, `camera_geometry.py` |
| 2026-02-28 | Preview rendering pipeline | [0008](../adr/0008-hour-four-preview-architecture.md) | `previews.py`, `preview_renderer.py`, `render-preview-inner.tsx` |
| 2026-02-28 | MCP server v1.0-1.1 (3 tools) | — | `mcp/server.py`, `mcp/tools_*.py` |
| 2026-03-01 | Precise point elevation sampler | [0009](../adr/0009-precise-point-elevation-and-agl-camera-safety.md) | `tiles.py`, `terrarium.py` |
| 2026-03-01 | Three-layer AGL camera safety | [0009](../adr/0009-precise-point-elevation-and-agl-camera-safety.md) | `camera_safety.py`, `style_matching.py`, `previews.py`, `preview_renderer.py`, `render-preview-inner.tsx` |
| 2026-03-01 | Point context service + REST + MCP tool | [0009](../adr/0009-precise-point-elevation-and-agl-camera-safety.md) | `point_context.py`, `routes/terrain.py`, `mcp/tools_point_context.py` |
