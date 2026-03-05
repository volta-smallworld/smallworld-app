## High-Fidelity Map + Preview + Analysis Plan (Full Stack Now)

### Summary
Implement one coordinated delivery that raises fidelity in both user-facing surfaces:
1. Smallworld interactive map visual fidelity.
2. Preview render image fidelity.
3. Terrain-analysis fidelity feeding viewpoints (shared by Smallworld + chat tools).

This plan uses the selected strategy:
- Provider strategy: **Google + Ion Hybrid**.
- Delivery scope: **Full Stack Now**.
- Key model: **Browser Google key with strict referrer restrictions**.
- DEM scope: **Terrarium+ upgrades now** (no Copernicus migration in this delivery).

### Goals and success criteria
1. Map no longer appears low-fidelity when credentials are present.
2. Preview render success + quality improve, with deterministic fallback behavior.
3. Viewpoint inputs are more accurate from higher-resolution DEM sampling.
4. Changes are additive/backward-compatible for existing endpoints and chat tools.

Success thresholds:
- Map provider selection works by priority: `google3d -> ionTerrain -> osm`.
- Preview provider selection works by priority with automatic retry/fallback.
- Terrain routes return same core payloads and stay compatible; new fidelity metadata is additive.
- No regression in existing terrain/chat flows when keys are absent.

### Scope
In scope:
- Provider capability resolution and fallback for map + previews.
- Interactive map terrain/imagery upgrades.
- Preview rendering pipeline fidelity upgrades.
- DEM fidelity upgrades on current Terrarium source.
- Tests, docs, and rollout guidance.

Out of scope for this delivery:
- Copernicus GLO-30 migration.
- OSM vector footprint ingestion/3D-volume landmark centering.
- Composition algorithm redesign.

---

## Implementation plan

### 1) Unify fidelity capability model (shared decision engine)
Files to update:
- [apps/web/src/lib/cesium.ts](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/web/src/lib/cesium.ts)
- [apps/web/src/lib/server/preview-capabilities.ts](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/web/src/lib/server/preview-capabilities.ts)
- [apps/api/src/smallworld_api/config.py](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/api/src/smallworld_api/config.py)

Decisions:
- Map provider order: `google3d`, then `ionTerrain`, then `osm`.
- Preview provider order: `google3d`, then `ionTerrain`, then `osm/ellipsoid`.
- Browser-facing Google key uses `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`.
- Browser-facing Ion token uses `NEXT_PUBLIC_CESIUM_ION_TOKEN`.
- Backend preview renderer continues using `GOOGLE_MAPS_API_KEY` and `CESIUM_ION_TOKEN`.

Implementation details:
- Add explicit provider-resolution utility used by map and preview capability endpoint.
- Keep behavior deterministic and observable (return selected provider + available providers).
- Keep no-key experience functional (OSM fallback).

### 2) Upgrade Smallworld interactive map fidelity
Files to update:
- [apps/web/src/components/cesium-map.tsx](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/web/src/components/cesium-map.tsx)
- [apps/web/src/lib/cesium.ts](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/web/src/lib/cesium.ts)

Changes:
- If Google key exists: load Google Photorealistic 3D Tiles as primary (existing behavior stays, hardened with provider state).
- If Google absent but Ion token exists: instantiate Cesium World Terrain + Ion imagery (satellite) instead of OSM-only flat globe.
- If neither exists: OSM + ellipsoid fallback (current baseline).
- Add lightweight map fidelity status indicator in UI state (provider badge) so users and debugging can confirm active mode.

Acceptance:
- With only `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`, map shows photorealistic 3D.
- With only `NEXT_PUBLIC_CESIUM_ION_TOKEN`, map shows non-flat terrain with higher-fidelity imagery.
- With neither, map still loads and behaves as today.

### 3) Upgrade preview render fidelity and fallback behavior
Files to update:
- [apps/web/src/app/render/preview/render-preview-inner.tsx](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/web/src/app/render/preview/render-preview-inner.tsx)
- [apps/api/src/smallworld_api/services/previews.py](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/api/src/smallworld_api/services/previews.py)
- [apps/api/src/smallworld_api/services/preview_renderer.py](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/api/src/smallworld_api/services/preview_renderer.py)

Changes:
- Preserve current first attempt with Google 3D when backend key is present.
- Add explicit second attempt with Ion terrain/imagery when Google fails and Ion token exists.
- Keep final fallback path that can render without premium providers.
- Raise default preview resolution to `1920x1080` for better detail while preserving request override.
- Keep existing terrain clamp and diagnostics.

Acceptance:
- Preview renders succeed even when Google tiles fail (fallback observed in attempts metadata).
- Higher visual detail at defaults without breaking timeout behavior.
- Chat `preview_render_pose` benefits automatically because it uses the same pipeline.

### 4) Increase terrain-analysis fidelity on Terrarium (Terrarium+)
Files to update:
- [apps/api/src/smallworld_api/config.py](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/api/src/smallworld_api/config.py)
- [apps/api/src/smallworld_api/services/terrarium.py](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/api/src/smallworld_api/services/terrarium.py)
- [apps/api/src/smallworld_api/routes/terrain.py](/Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/apps/api/src/smallworld_api/routes/terrain.py)

Decisions:
- `default_terrarium_zoom`: `12 -> 13`.
- `max_tiles_per_request`: `36 -> 64`.
- Replace nearest-neighbor grid resample with bilinear interpolation.
- Keep grid contract at `128x128` (compatibility).

Changes:
- Update crop/resample to bilinear for smoother and less aliasing-prone elevation grids.
- Keep current adaptive zoom downshift logic when tile cap is exceeded.
- Add in-memory decoded tile cache (LRU + TTL) to reduce repeated tile fetch latency for nearby requests and point samples.

Acceptance:
- Terrain endpoints remain schema-compatible.
- `zoomUsed` typically increases in same-area requests (subject to cap).
- Viewpoints become more stable in complex terrain due to better input resolution + interpolation.

### 5) Add additive fidelity metadata to public responses (no breaking changes)
Public interface updates:
- Terrain responses (`/api/v1/terrain/elevation-grid`, `/analyze`, `/viewpoints`) add additive `fidelity` object:
  - `demProvider`
  - `zoomRequested`
  - `zoomUsed`
  - `gridWidth`
  - `gridHeight`
  - `resampleMethod`
  - `tileCount`
- Web preview capabilities response (`/api/viewpoint-previews/capabilities`) adds additive fields:
  - `availableProviders`
  - `providerOrder`
  - `activeProvider`

Type updates:
- Update corresponding TS and Pydantic response models as additive optional fields first, then required once end-to-end usage is wired.

### 6) Environment and security hardening
Files to update:
- Root env docs/example files and README sections.

Changes:
- Document split keys clearly:
  - Browser: `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`, `NEXT_PUBLIC_CESIUM_ION_TOKEN`
  - Backend: `GOOGLE_MAPS_API_KEY`, `CESIUM_ION_TOKEN`
- Require Google browser key to be referrer-restricted (prod and staging domains).
- Keep backend key server-only for API preview pipeline.

Acceptance:
- Local/dev setup clearly guides how to enable each fidelity tier.
- No accidental dependency on a single provider.

### 7) Testing and validation
Unit tests:
- Bilinear resample correctness on synthetic DEM gradients.
- Provider resolver logic (all key permutations).
- Tile cache hit/miss/expiry behavior.

API/integration tests:
- Terrain route contracts unchanged except additive metadata.
- Preview pipeline retry order verified via mocked provider failures.
- Warning/attempt metadata correctness for fallback scenarios.

UI/e2e tests:
- Map provider selection: Google mode, Ion mode, OSM mode.
- Preview render endpoint works in each provider mode and returns image.
- Regression check: no-key environment still fully usable.

Manual acceptance script:
- Compare before/after screenshots for map and preview in same coordinates.
- Validate chat flow still produces previews and viewpoint results.

### Rollout plan
1. Deploy backend + web with additive fields and fallback logic.
2. Enable browser Google key (restricted) in staging; verify provider badge + map quality.
3. Enable in production.
4. Monitor preview fallback frequency and render time.
5. If render latency increases too much, tune default resolution or timeout without reverting provider logic.

---

## Assumptions and locked defaults
- This delivery does **not** include Copernicus migration.
- This delivery does **not** include OSM vector shape/footprint ingestion.
- Full-stack-now means: map visuals + preview visuals + Terrarium analysis fidelity upgrades in one implementation cycle.
- Backward compatibility is required for existing chat and API consumers.
- Google browser key will be provisioned with strict referrer restrictions before production enablement.
