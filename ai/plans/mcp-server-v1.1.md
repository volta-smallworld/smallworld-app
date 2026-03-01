# Smallworld MCP Server v1.1: Terrain, Viewpoints, and Preview Rendering

## Summary
Replace the current terrain-only MCP v1 scope with an explicit three-tool MCP server that supports the actual Smallworld agent flow: analyze terrain, generate ranked viewpoints, and render a preview from a chosen pose.

Keep the current architectural choices that still fit:
- Python backend stack
- FastMCP
- explicit hand-authored tool contracts
- separate process with `stdio` and Streamable HTTP
- no HTTP self-calls from MCP into FastAPI routes

Add one compatibility-critical change: the preview endpoint plan must expose a shared preview orchestration service so the FastAPI preview route and the MCP preview tool use the same render, enhancement, artifact, and verification pipeline.

## Important Changes Or Additions To Public APIs/Interfaces/Types
Existing REST routes remain additive and unchanged, including:
- `GET /healthz`
- `POST /api/v1/terrain/elevation-grid`
- `POST /api/v1/terrain/viewpoints`
- the planned preview routes:
  - `POST /api/v1/previews/render`
  - `GET /api/v1/previews/{preview_id}/artifacts/{variant}`

The MCP server will expose three tools and two resources.

### MCP tools
`terrain_analyze_area`
- Same purpose as the current MCP plan.
- Input stays compact: `lat`, `lng`, `radius_meters`, `zoom`, `include_elevations`.
- Output stays compact and excludes the elevation matrix unless requested.

`terrain_find_viewpoints`
- Purpose: expose the existing viewpoint-generation pipeline in an agent-friendly schema and return preview-ready inputs.
- Input:
  - `lat`
  - `lng`
  - `radius_meters`
  - `weights?`
  - `compositions?`
  - `max_viewpoints?`
  - `max_per_scene?`
  - `include_preview_input?` default `true`
- Output:
  - `request`
  - `summary`
  - `viewpoints[]`
  - `source`

Each returned viewpoint must include:
- `id`
- `scene`
- `composition`
- `camera`
- `targets`
- `distance_meters_approx`
- `score`
- `score_breakdown`
- `validation`
- `preview_input` when `include_preview_input=true`

`preview_render_pose`
- Purpose: render one preview from an explicit camera pose plus scene/composition context, optionally enhance it, and surface stored artifact locations.
- Input:
  - `camera`
  - `scene`
  - `composition`
  - `viewport?`
  - `enhancement?`
- Output:
  - `id`
  - `status`
  - `warnings`
  - `raw_image`
  - `enhanced_image?`
  - `metadata`
  - `timings_ms`
  - `manifest_path`

### MCP resources
Keep:
- `smallworld://server-info`
- `smallworld://usage-guidance`

Update `smallworld://server-info` to expose:
- enabled transports
- enabled tools
- terrain defaults
- viewpoint defaults
- preview capability flags:
  - `renderer_configured`
  - `enhancement_configured`
  - `artifact_url_base_configured`

Update `smallworld://usage-guidance` to describe the intended chain:
1. `terrain_analyze_area`
2. `terrain_find_viewpoints`
3. `preview_render_pose` using `viewpoints[n].preview_input`

### MCP-specific schema rules
Normalize MCP-facing composition enums to snake_case:
- `rule_of_thirds`
- `golden_ratio`
- `leading_line`
- `symmetry`

Add MCP-specific models in `apps/api/src/smallworld_api/mcp/schemas.py`:
- `TerrainAnalyzeAreaInput`
- `TerrainAnalyzeAreaResult`
- `TerrainFindViewpointsInput`
- `McpCompositionType`
- `McpCameraPose`
- `McpViewpointTarget`
- `McpPreviewAnchor`
- `McpPreviewInput`
- `McpViewpoint`
- `PreviewRenderPoseInput`
- `PreviewArtifactRef`
- `PreviewRenderPoseResult`
- `PreviewWarning`

Define `preview_input` so it can be passed directly into `preview_render_pose` without extra transformation. It must contain the full required preview payload except optional viewport and enhancement overrides:

```json
{
  "camera": {
    "position": {
      "lat": 39.745812,
      "lng": -104.998164,
      "alt_meters": 2412.3
    },
    "heading_deg": 113.5,
    "pitch_deg": -8.4,
    "roll_deg": 0.0,
    "fov_deg": 55.0
  },
  "scene": {
    "center": {
      "lat": 39.7392,
      "lng": -104.9903
    },
    "radius_meters": 5000,
    "scene_id": "scene-2",
    "scene_type": "peak-ridge",
    "scene_summary": "Prominent summit with connecting skyline ridge",
    "feature_ids": ["peak-1", "ridge-1"]
  },
  "composition": {
    "target_template": "rule_of_thirds",
    "subject_label": "primary summit",
    "horizon_ratio": 0.333,
    "anchors": [
      {
        "id": "peak-1",
        "label": "primary",
        "lat": 39.742,
        "lng": -104.981,
        "alt_meters": 2180,
        "desired_normalized_x": 0.667,
        "desired_normalized_y": 0.333
      }
    ]
  }
}
```

Define preview artifact refs as:

```json
{
  "local_path": "/abs/path/to/.preview_artifacts/preview_.../raw.png",
  "url": "http://127.0.0.1:8000/api/v1/previews/preview_.../artifacts/raw",
  "mime_type": "image/png",
  "width": 1536,
  "height": 1024
}
```

`local_path` is always present on success. `url` is present only when `PREVIEW_PUBLIC_BASE_URL` is configured.

## Implementation Plan
1. Keep the MCP server under `apps/api/src/smallworld_api/mcp` as a separate FastMCP entrypoint with `stdio` and Streamable HTTP modes.

2. Split MCP code by concern:
- `server.py`
- `cli.py`
- `resources.py`
- `schemas.py`
- `adapters.py`
- `tools_terrain.py`
- `tools_viewpoints.py`
- `tools_previews.py`

3. Keep the direct-service rule from the current MCP plan. MCP tools must not call FastAPI routes over HTTP.

4. Add a shared preview orchestration service at `apps/api/src/smallworld_api/services/previews.py`.
This is the compatibility-critical change.
`routes/previews.py` from the preview endpoint plan must become a thin HTTP adapter that validates the request, calls `services.previews.render_preview(...)`, and maps the shared result into the REST response.
`tools_previews.py` must call the same `render_preview(...)` function and map the shared result into the MCP result shape.

5. Keep the preview plan’s low-level support modules:
- `preview_renderer.py`
- `preview_enhancement.py`
- `preview_artifacts.py`
- `composition_verifier.py`

`services/previews.py` orchestrates those modules. Neither the route nor the MCP tool duplicates that logic.

6. Add a viewpoint-to-preview adapter in `mcp/adapters.py`.
It must:
- map existing camelCase viewpoint compositions to snake_case MCP compositions
- map `altitudeMeters` to `alt_meters`, `headingDegrees` to `heading_deg`, and similar camera fields
- reconstruct scene context from the original viewpoint search request plus the chosen scene
- construct preview anchors from selected feature geometry and template target placements

7. Support step 6 by enriching the internal viewpoint generation path so anchor geometry is available before REST serialization.
Do not change the existing REST `ViewpointSearchResponse`.
Instead, change the internal viewpoint generation flow so it can return richer internal viewpoint data that includes:
- selected anchor feature dicts
- scene center and feature IDs
- template metadata
- target placements
- preview-ready anchor coordinates

The REST route can strip those internal fields before returning its current response shape. The MCP adapter can use the richer internal shape to build `preview_input` deterministically.

8. Keep MCP schemas explicit and hand-designed.
Do not mirror the preview REST contract verbatim.
Use snake_case everywhere in MCP and expose `preview_input` objects that agents can chain directly.

9. Add `PREVIEW_PUBLIC_BASE_URL` to `apps/api/src/smallworld_api/config.py`.
Purpose: allow the MCP preview tool to emit absolute artifact URLs when the FastAPI API server is reachable.
If unset, the MCP preview tool returns `url=null` and still succeeds.

10. Reuse the preview endpoint plan’s preview settings rather than inventing MCP-specific duplicates:
- `preview_artifacts_dir`
- `preview_artifact_ttl_hours`
- `preview_renderer_base_url`
- `preview_render_timeout_seconds`
- `preview_default_width`
- `preview_default_height`
- `preview_default_fov_deg`
- `cesium_ion_token`
- `mapbox_access_token`
- `gemini_api_key`
- `gemini_image_model`

11. Keep the current MCP HTTP defaults:
- host `127.0.0.1`
- port `8001`
- path `/mcp`

Keep env overrides:
- `MCP_HTTP_HOST`
- `MCP_HTTP_PORT`
- `MCP_HTTP_PATH`

12. Update root developer scripts in `package.json`:
- `dev:mcp`
- `dev:mcp:http`
- `test:mcp`

13. Update docs:
- root README with MCP setup and run instructions
- an ADR explaining:
  - explicit tool design
  - dual transport
  - separate process
  - why preview rendering uses a shared application service instead of HTTP self-calls

## Operational Behavior And Error Handling
- Validation failures must fail before any terrain, viewpoint, or preview service work starts.
- `terrain_analyze_area` keeps the current MCP behavior:
  - tile-cap overflow becomes a clear tool error asking the caller to reduce radius
  - upstream tile fetch failures become short retryable tool errors
- `terrain_find_viewpoints` uses the existing terrain/viewpoint stack and must surface:
  - the same validation bounds as the current REST route
  - tile fetch failures as retryable tool errors
  - empty valid results as success with `viewpoints=[]`
- `preview_render_pose` uses the preview endpoint plan’s success policy:
  - missing renderer config becomes a tool error equivalent to REST `503`
  - render timeout becomes a tool error equivalent to REST `504`
  - render subprocess failure becomes a tool error equivalent to REST `502`
  - missing enhancement config is not a tool error; return success with raw artifact only, `status=completed_with_warnings`, and warning code `enhancement_not_configured`
  - enhancement runtime failure is not a tool error; return success with raw artifact only, `status=completed_with_warnings`, and warning code `enhancement_failed`
  - missing `PREVIEW_PUBLIC_BASE_URL` is not a warning; return only `local_path`
- Treat preview rendering as computational artifact generation, not a domain mutation. This replaces the current plan’s blanket “read-only tools only” restriction.
- The MCP server remains stateless across requests. Artifact files are the only persistent side effect and are managed by the shared preview artifact service and TTL cleanup.

## Test Cases And Scenarios
- Tool registration test: the server lists exactly three tools and two resources.
- `terrain_analyze_area` happy path with `include_elevations=false` returns stats, bounds, tiles, and `elevations=null`.
- `terrain_analyze_area` happy path with `include_elevations=true` returns a `128x128` matrix.
- `terrain_find_viewpoints` happy path returns ranked viewpoints in score order and includes `preview_input` by default.
- `terrain_find_viewpoints` with `include_preview_input=false` omits `preview_input` and still returns the same rankings.
- `terrain_find_viewpoints` maps compositions to snake_case MCP values while preserving the underlying viewpoint ordering and scores.
- `terrain_find_viewpoints` preview inputs include enough anchor geometry to call `preview_render_pose` without extra lookups.
- `preview_render_pose` success returns `raw_image.local_path` always and `enhanced_image` when enhancement succeeds.
- `preview_render_pose` returns `url` fields when `PREVIEW_PUBLIC_BASE_URL` is set and `url=null` when it is not.
- `preview_render_pose` enhancement failure returns success with warning and raw artifact only.
- `preview_render_pose` missing renderer config returns a stable tool error rather than crashing the server.
- Resource read test for `smallworld://server-info`.
- Resource read test for `smallworld://usage-guidance`.
- Stdio smoke test:
  1. initialize a client session
  2. list tools
  3. call `terrain_find_viewpoints`
  4. call `preview_render_pose` with `viewpoints[0].preview_input`
- Streamable HTTP smoke test:
  1. start the server on `/mcp`
  2. initialize a client session
  3. list tools
  4. call `terrain_find_viewpoints`
  5. call `preview_render_pose`
- Backward-compatibility test: existing FastAPI terrain and viewpoint route tests continue to pass unchanged.
- Companion-plan compatibility test: the FastAPI preview route and the MCP preview tool return the same metadata, warning semantics, and artifact IDs for the same mocked render request.

## Acceptance Criteria
- A local MCP client can connect over `stdio`, discover all three tools, and chain viewpoint discovery into preview rendering without inventing camera poses manually.
- A remote/internal MCP client can connect to `http://localhost:8001/mcp` and perform the same flow.
- `terrain_find_viewpoints` reuses the current viewpoint pipeline and preserves the same ranking behavior as the REST implementation.
- `preview_render_pose` reuses the same shared preview orchestration as the FastAPI preview endpoint and produces the same render, enhancement, and composition-verification behavior.
- On preview success, the MCP result always contains a raw artifact `local_path`.
- When `PREVIEW_PUBLIC_BASE_URL` is configured, the MCP result also contains API artifact URLs that point at the preview endpoint plan’s artifact route.
- Existing web app behavior and existing terrain/viewpoint REST contracts do not change.

## Assumptions And Defaults
- This plan replaces the current terrain-only MCP v1 scope.
- The MCP surface remains explicit and hand-designed; auto-generated “wrap every endpoint” approaches stay out of scope.
- The server stays in Python and remains a separate process in v1.
- Remote HTTP support remains trusted/internal only; public internet auth and OAuth are deferred.
- Prompts remain out of scope in v1.
- MCP-facing contracts use snake_case even when existing REST contracts use camelCase.
- The preview endpoint plan remains the public HTTP contract for preview rendering, but its orchestration must live in a shared service so REST and MCP stay consistent.
- The preview tool accepts explicit camera pose input only; it does not add new camera-solving behavior beyond the existing viewpoint generator.
- Inline image bytes are out of scope; artifact delivery is paths first, URLs second.
