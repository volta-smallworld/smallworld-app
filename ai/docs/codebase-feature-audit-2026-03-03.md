# Smallworld Codebase Feature Audit (2026-03-03)

## Scope

This audit covers the full monorepo:

- `apps/api` (FastAPI + MCP + algorithm services)
- `apps/web` (map UI + chat UI + preview rendering routes)
- automated backend validation via `pnpm test:api`

## Validation Method

1. Traced runtime entrypoints from web routes and API routers into services.
2. Confirmed MCP tool inventory and chat orchestration behavior.
3. Verified feature tests using `pnpm test:api` (294 passed).
4. Classified features as:
   - `implemented`
   - `partially_wired`
   - `not_wired`

## Executive Summary

- Core terrain-to-viewpoint pipeline is implemented and exercised.
- Composition-aware camera solving is real (optimization + geometric constraints), not just random search.
- Beauty scoring is implemented with 7 DEM-derived metrics and is used for ranking.
- Render pipeline (headless Cesium + optional Gemini enhancement) is implemented and used.
- "LLM can move and adjust camera parameters" is implemented via session artifacts and tool calls.
- "LLM can see/inspect rendered images" is currently not true in the active chat path.
- Gemini self-critique service exists but is not wired into any runtime pipeline.
- Style matching is implemented, but parts of the verification loop are not fully connected in the web flow.

## End-to-End Pipelines

### A) Terrain Explorer UI pipeline (`/`)

1. User selects map center/radius.
2. Web calls:
   - `/api/v1/terrain/analyze`
   - `/api/v1/terrain/viewpoints`
   - optional style routes (`/api/v1/style-references`, `/api/v1/terrain/style-viewpoints`)
3. API computes DEM -> features -> hotspots -> scenes -> viewpoints.
4. Viewpoint preview cards call `/api/viewpoint-previews` (legacy web-side renderer path).

Status: `implemented`, but preview path here is legacy and bypasses API preview enhancement/composition verification.

### B) Chat + MCP pipeline (`/chat`, `/chat-v2`, `/chat-v3`)

1. User prompt -> `/api/chat`.
2. Chat orchestrator discovers MCP tools and runs tool-use rounds with Anthropic.
3. Typical tool chain:
   - `terrain_analyze_area`
   - `terrain_find_viewpoints`
   - `preview_render_pose`
4. `preview_render_pose` calls shared API render pipeline with clamp/enhancement/verification.
5. UI shows rendered image via `/api/previews/{id}/{raw|enhanced}` proxy route.

Status: `implemented`.

## Feature Inventory

### Terrain Acquisition and Analysis

- DEM tile math, fetch, decode, stitch, crop/resample: `implemented`
- Single-point precise elevation (bilinear on raw Terrarium tiles): `implemented`
- Terrain derivatives (slope/curvature/relief): `implemented`
- Feature extraction (peaks/ridges/cliffs/water channels): `implemented`
- Interest raster, hotspots, scene grouping: `implemented`

Usage:
- Used by REST routes and MCP terrain tools.

### Viewpoint Generation and "Aesthetic Angles"

- Composition templates (rule of thirds, golden ratio, leading line, symmetry): `implemented`
- Camera solving:
  - PnP least-squares solver for most templates
  - constructive solver for leading-line
- Candidate validation:
  - bounds
  - terrain clearance
  - line-of-sight visibility
- Ranking:
  - 7-factor proxy beauty score:
    - viewshed richness
    - terrain entropy
    - skyline fractal
    - prospect-refuge
    - depth layering
    - mystery
    - water visibility

Usage:
- Called by `/api/v1/terrain/viewpoints`, MCP `terrain_find_viewpoints`, and style viewpoint pipeline.

Assessment of "are we actually finding aesthetically pleasing angles?":
- The code does algorithmically enforce composition targets and optimize camera pose.
- It does not include human preference testing or learned aesthetic ground truth; quality is proxy-metric driven.
- So: algorithmic composition + heuristic aesthetics are active; perceptual "pleasing" is approximate, not proven against user studies.

### Preview Rendering + Enhancement

- Headless Cesium/Puppeteer render pipeline: `implemented`
- Multi-layer camera safety (pre-render clamp + renderer terrain clamp): `implemented`
- Optional Gemini enhancement: `implemented`
- Composition verification metadata: `implemented` (with caveats)

Usage:
- Fully used by MCP `preview_render_pose` and `/api/v1/previews/render`.

### Style Reference System

- Style reference upload + fingerprint extraction: `implemented`
- DEM patch matching and style-aware re-ranking: `implemented`
- Render verification endpoint (CLIP + LPIPS + edge): `implemented`

Usage:
- Style search endpoint is wired in web `/`.
- Verification endpoint exists but is not actively invoked in the current `/` flow.

Status: `partially_wired`.

### LLM Spatial/Control Features

- Tool-based spatial context (`terrain_point_context`): `implemented`
- Iterative camera adjustment across chat turns (artifact memory): `implemented`
- Parameter edits (heading/pitch/fov/alt/position/composition): `implemented` in system prompt rules

Status: `implemented`.

### LLM Vision and Self-Critique Claims

- LLM directly "looking at" rendered image in chat loop: `not_wired`
- Gemini `render_critic` self-critique with pose deltas: service exists but runtime integration: `not_wired`

## Key Findings / Gaps

1. `partially_wired`: style synthetic scenes use type `"style-patch"` but composition templates do not allow that scene type, so those synthesized scenes cannot generate viewpoints through the normal template filter.
2. `partially_wired`: composition verification currently uses original requested altitude, not always the post-clamp altitude used for final render metadata.
3. `not_wired`: chat MCP client currently keeps only text parts from tool results, so inline image payloads are not fed back to the model for visual reasoning.
4. `not_wired`: `render_critic` service is tested but not exposed through API route, MCP tool, or preview orchestration loop.
5. `partially_wired`: `/api/viewpoint-previews` (map card previews) uses a separate legacy web render path and does not run API-side enhancement/composition verification.
6. `partially_wired`: style verification UI state is displayed but not updated by active verification calls in current page flow.

## Test Evidence

Backend test suite run:

- Command: `pnpm test:api`
- Result: `294 passed`

This validates core algorithm/service behavior and route contracts in `apps/api`.

## Bottom Line

The core algorithmic pipeline is operational and substantial. Camera composition and ranking logic are not superficial; they are actively computed and used. The biggest deltas between aspiration and current runtime are in closed-loop AI vision/self-critique and full wiring of style verification paths.
