# ADR 0009: Precise Point Elevation and Multi-Layer AGL Camera Safety

- Status: Accepted
- Date: 2026-03-01
- Deciders: smallworld maintainers
- Related: [ADR 0006](./0006-use-aws-terrarium-tiles-for-hour-one-dem-source.md), [ADR 0008](./0008-hour-four-preview-architecture.md)

## Context

Camera-inside-mountain failures occur in the preview rendering pipeline because:

1. **Coarse grid resolution**: The 128x128 resampled DEM grid (from ADR 0007) is too coarse for precise single-point ground elevation sampling. A cell can be 50-100m wide, smoothing over peaks and valleys.
2. **Terrain source mismatch**: The backend analyzes terrain using AWS Terrarium DEM tiles, while the renderer uses Cesium World Terrain or Google 3D Tiles for actual geometry. A camera position that clears the DEM may still be underground in the rendered world.

These failures produce unusable preview images and degrade the AI pipeline's ability to generate valid landscape photographs.

## Decision Drivers

- Camera-inside-terrain is the most visually catastrophic failure mode in the preview pipeline
- A single defense layer is insufficient due to the terrain source mismatch
- Solutions must not add latency to the happy path (camera already above ground)
- Existing infrastructure (Terrarium tiles, Cesium APIs) should be reused rather than introducing new data sources

## Options Considered

- Option A: Increase DEM grid resolution from 128x128 to 512x512. Would reduce but not eliminate the coarseness problem, and would not address the terrain source mismatch. Significant memory and bandwidth cost.
- Option B: Add a fixed safety margin to all camera altitudes. Simple but wastes vertical range — low-angle shots would be pushed unnecessarily high.
- Option C: Multi-layer AGL (Above Ground Level) enforcement with precise point sampling. Three independent defense layers using different terrain sources, each progressively closer to the actual render geometry.

## Decision

Adopt Option C: multi-layer AGL camera safety with a new precise point elevation sampler.

Three defense layers enforce a minimum AGL floor (default 5m):
1. **Post-refinement** (style matching): Sync DEM-based clamp using the already-loaded 128x128 grid — catches gross violations with zero network cost.
2. **Pre-render** (preview pipeline): Async precise tile sampling at zoom 14 — uses raw 256x256 Terrarium tiles with bilinear interpolation for ~10m accuracy.
3. **Renderer-side** (Cesium client): Native terrain sampling using the actual render geometry — final defense against source mismatch.

## Decision Details

### Precise point sampler
- Uses raw 256x256 Terrarium tiles (never the 128x128 resampled grid)
- Bilinear interpolation across tile boundaries, fetching 1-4 tiles as needed
- Default zoom 14 (~10m/pixel at mid-latitudes), configurable via `POINT_ELEVATION_DEFAULT_ZOOM`
- Antimeridian wrapping: `(tile_x + 1) % 2^zoom`
- Mercator latitude clamped to ±85.05 before projection

### AGL floor enforcement
- Default floor: 5.0m (configurable via `CAMERA_AGL_FLOOR_METERS`)
- Both sync (DEM-based) and async (precise tile) variants share the same `CameraSafetyResult` dataclass
- When clamped: altitude set to `ground + floor`, original altitude preserved in metadata

### Renderer-side clamp
- Uses `sampleTerrainMostDetailed` for Cesium World Terrain
- Uses `scene.sampleHeightMostDetailed` for Google 3D Tiles (globe is hidden in that mode)
- Wrapped in `Promise.race` with configurable timeout (default 3000ms)
- Single retry on sample failure
- Results recorded in `__SMALLWORLD_FRAME_STATE__.terrainClamp`

### Explicit exclusions
- No new external data sources introduced
- No changes to the 128x128 grid contract (ADR 0007)
- Renderer clamp is best-effort — sample failure does not block rendering

## Consequences

- Camera-inside-terrain failures are eliminated or significantly reduced across all three pipeline stages
- The point elevation sampler is independently useful for terrain queries (exposed as REST and MCP endpoints)
- Additional 1-4 tile fetches per pre-render check add ~100-200ms latency, but only when the pipeline runs
- Renderer-side sampling may time out on slow connections, in which case rendering proceeds without the clamp
- Warning codes (`camera_clamped_above_terrain`, `renderer_terrain_clamp_applied`, etc.) provide observability into clamp activity

## Implementation Notes

### New config settings (`config.py`)
- `POINT_ELEVATION_DEFAULT_ZOOM` (default: 14)
- `CAMERA_AGL_FLOOR_METERS` (default: 5.0)
- `RENDERER_TERRAIN_CLAMP_ENABLED` (default: true)
- `RENDERER_TERRAIN_SAMPLE_TIMEOUT_MS` (default: 3000)

### New files
- `services/camera_safety.py` — `enforce_agl_floor_precise()`, `enforce_agl_floor_dem()`
- `services/point_context.py` — `get_point_context()` combining precise elevation with local terrain analysis
- `mcp/tools_point_context.py` — MCP tool registration

### New API endpoint
- `POST /api/v1/terrain/point-context` — precise ground elevation + optional AGL + local terrain context

### New MCP tool
- `terrain_point_context` — fourth tool, exposes point context to AI agents

### Modified pipeline files
- `services/style_matching.py` — DEM-based AGL floor after style refinement
- `services/previews.py` — precise AGL floor before render + diagnostic propagation after render
- `services/preview_renderer.py` — `safety` block in renderer payload
- `render-preview-inner.tsx` — Cesium-side terrain clamp with timeout and retry

### Warning codes (in preview pipeline output)
- `camera_clamped_above_terrain` — pre-render clamp applied
- `terrain_sample_unavailable` — pre-render terrain sample failed
- `renderer_terrain_clamp_applied` — renderer-side clamp applied
- `renderer_terrain_sample_failed` — renderer could not sample terrain

## Validation

- All 294 backend tests pass, including new tests for point elevation, camera safety, point context, route, and MCP tool
- Web linting passes with zero errors
- `enforce_agl_floor_dem` correctly clamps underground cameras and preserves above-ground cameras
- `sample_point_elevation` returns correct elevation for uniform tiles and handles tile boundaries
- MCP server reports 4 tools and 2 resources
- Point-context route returns 200 with valid data, 422 for invalid input, 502 for upstream failures

## Follow-ups

- Measure clamp frequency in production to tune the default floor
- Consider caching Terrarium tiles to reduce repeated fetches for nearby points
- Evaluate whether renderer-side clamp should block rendering on repeated failure (currently best-effort)
- Add integration test that verifies end-to-end clamp across all three layers with a known mountainous location
