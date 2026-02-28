# Hour 1 Implementation Plan: Foundation Slice

## Summary
Build a greenfield monorepo with `apps/web` and `apps/api`, then ship the first end-to-end terrain pipeline:

1. A Next.js App Router frontend with a token-free Cesium globe.
2. A FastAPI backend with CORS and a stable terrain endpoint.
3. Click-to-select map center plus a radius slider.
4. AWS Terrarium tile fetch + decode on the backend.
5. A bounded, fixed-size elevation grid response rendered in a simple debug/results panel.

This hour-one slice is complete when a user can open the app locally, click a location, set a radius, request terrain data, and see decoded elevation metadata come back from the API.

## Scope

### In scope
- Monorepo bootstrap in the empty repo
- `apps/web` using Next.js App Router + TypeScript
- `apps/api` using FastAPI + Python 3.12 + `uv`
- Cesium globe with click selection
- Radius control via slider
- `POST` terrain endpoint returning a fixed analysis grid
- Terrarium PNG decoding to elevation in meters
- Loading, error, and success states
- Minimal automated tests on the backend
- Basic frontend smoke validation and clear local run docs

### Out of scope
- Terrain derivatives, feature extraction, peaks, ridges, scoring
- Headless rendering
- Style reference upload
- Persistence, auth, user accounts
- Fancy map overlays beyond center marker and radius ellipse

## Repo Layout
Use a simple monorepo without Turbo for hour one.

```text
/
  package.json
  pnpm-workspace.yaml
  .gitignore
  README.md
  apps/
    web/
      package.json
      next.config.mjs
      tsconfig.json
      public/
      src/
        app/
          layout.tsx
          page.tsx
          globals.css
        components/
          cesium-map.tsx
          control-panel.tsx
          terrain-result-panel.tsx
        lib/
          api.ts
          cesium.ts
        types/
          terrain.ts
    api/
      pyproject.toml
      README.md
      src/
        smallworld_api/
          main.py
          config.py
          models/
            terrain.py
          routes/
            terrain.py
          services/
            terrarium.py
            tiles.py
      tests/
        test_terrain_route.py
        test_terrarium_decode.py
        test_tile_math.py
```

## Important Changes Or Additions To Public APIs/Interfaces/Types

### Environment variables
- Web:
  - `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
- API:
  - `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`
  - `TERRARIUM_TILE_URL_TEMPLATE=https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`
  - `DEFAULT_TERRARIUM_ZOOM=12`
  - `MAX_TILES_PER_REQUEST=36`

### Backend API
Add:
- `GET /healthz`
- `POST /api/v1/terrain/elevation-grid`

Request body:
```json
{
  "center": {
    "lat": 39.7392,
    "lng": -104.9903
  },
  "radiusMeters": 5000
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
    "cellSizeMetersApprox": 78.1,
    "elevations": [[1609.2, 1610.0]]
  },
  "tiles": [
    { "z": 12, "x": 852, "y": 1552 }
  ],
  "stats": {
    "minElevation": 1532.4,
    "maxElevation": 2488.9,
    "meanElevation": 1921.7
  },
  "source": "aws-terrarium"
}
```

### Validation rules
- `lat` must be between `-90` and `90`
- `lng` must be between `-180` and `180`
- `radiusMeters` must be between `1000` and `50000`
- If the tile coverage at the fixed zoom exceeds `MAX_TILES_PER_REQUEST`, return `422` with a clear message

### Frontend TypeScript types
Create shared web-local types matching the API contract:
- `MapSelection`
- `ElevationGridRequest`
- `ElevationGridResponse`
- `TerrainFetchState = "idle" | "loading" | "success" | "error"`

## Implementation Sequence

### 1. Bootstrap the monorepo
- Add root `package.json` with scripts:
  - `dev:web`
  - `dev:api`
  - `lint:web`
  - `test:api`
- Add `pnpm-workspace.yaml` for `apps/web`
- Keep Python isolated in `apps/api` with `uv`
- Add root `.gitignore` covering Next, Python, and local env files
- Add root `README.md` with setup and run commands

### 2. Stand up the FastAPI app
- Create `apps/api/pyproject.toml` with:
  - `fastapi`
  - `uvicorn[standard]`
  - `httpx`
  - `numpy`
  - `pillow`
  - `pydantic-settings`
  - `pytest`
- Add `main.py` with:
  - app creation
  - CORS middleware
  - router registration
  - `GET /healthz`
- Add `config.py` using `pydantic-settings`

### 3. Build the DEM service layer
- In `tiles.py`, implement:
  - center+radius to geographic bounds
  - bounds to slippy-map tile coverage at zoom 12
- In `terrarium.py`, implement:
  - Terrarium tile URL formatting
  - tile fetch via `httpx`
  - PNG decode via Pillow
  - Terrarium formula:
    - `elevation_m = (R * 256 + G + B / 256) - 32768`
  - tile stitching into one mosaic
  - bbox crop
  - resample to a fixed `128 x 128` analysis grid using NumPy
  - summary stats calculation
- Keep this code pure and testable outside the route layer

### 4. Expose the terrain route
- Add Pydantic request/response models in `models/terrain.py`
- Add `routes/terrain.py` with:
  - request validation
  - service call
  - error translation for oversized requests and upstream fetch failures
- Return a stable JSON contract even if the backend implementation changes later

### 5. Build the web app
- Create `apps/web` with Next.js App Router and TypeScript
- Add `cesium` and configure it in `next.config.mjs`
- Use a client-only `CesiumMap` component loaded with SSR disabled
- Configure Cesium assets under `/public/cesium`
- Use a token-free base setup:
  - ellipsoid globe
  - OpenStreetMap imagery
  - no Cesium Ion dependency for hour one
- Use a simple layout:
  - left: control panel
  - right: map and result panel

### 6. Implement the selection UX
- Clicking the globe sets `center.lat/lng`
- Show a marker entity at the selected center
- Radius is controlled with a slider in meters or kilometers
- Show the selected radius as an ellipse entity on the globe
- Add a `Fetch Terrain` button instead of auto-fetching on every change
- Show the selected coordinates and radius numerically in the control panel

### 7. Wire frontend to backend
- Add `lib/api.ts` with `fetchElevationGrid()`
- Read API base URL from `NEXT_PUBLIC_API_BASE_URL`
- On submit:
  - validate there is a selected center
  - call the FastAPI endpoint
  - store and render success or error state
- In the result panel, show:
  - bounds
  - tile count
  - min/max/mean elevation
  - grid dimensions
  - zoom used
- Do not attempt heatmap or terrain overlay in hour one

### 8. Handle failure paths cleanly
- Frontend:
  - disabled submit until a point is selected
  - loading spinner or busy state during fetch
  - visible inline error if request fails
- Backend:
  - `422` for invalid lat/lng/radius or too-large request
  - `502` if Terrarium tile fetch fails upstream
  - predictable JSON error payloads using FastAPI defaults

### 9. Document local development
- Root README should define:
  - how to install web deps with `pnpm`
  - how to sync API deps with `uv`
  - how to run web and API in separate terminals
  - expected local URLs
- Include one example request/response for the terrain endpoint

## Test Cases And Scenarios

### Backend automated tests
- `test_terrarium_decode.py`
  - verifies known RGB triplets decode to expected elevation values
- `test_tile_math.py`
  - center+radius produces expected bounds shape
  - bounds resolve to correct tile ranges
- `test_terrain_route.py`
  - valid request returns `200`
  - response shape includes `bounds`, `grid`, `tiles`, `stats`
  - grid is always `128 x 128`
  - invalid radius returns `422`
  - oversized tile request returns `422`

### Frontend validation
Use lightweight checks for hour one instead of a full browser test suite.
- API client unit test or smoke validation for request/response typing
- Manual validation scenarios:
  - page loads with globe visible
  - clicking globe updates selected coordinates
  - changing slider updates radius display and ellipse
  - clicking `Fetch Terrain` hits API and renders returned metadata
  - API failure renders a visible error state
  - submit is disabled before selection

## Acceptance Criteria
- `apps/web` starts locally and renders a Cesium globe
- `apps/api` starts locally and serves `GET /healthz`
- User can click a point on the globe and adjust radius
- User can submit the selection and receive decoded elevation data
- API returns a fixed-size bounded grid, not point samples
- CORS is configured so local web-to-api requests work without proxying
- The repo has enough docs and scripts that another engineer can run the stack without guessing

## Assumptions And Defaults
- Repo is intentionally greenfield; no existing app code needs preservation
- Frontend stack is Next.js App Router with TypeScript
- Web and API remain separate processes in hour one
- Cesium is token-free in this slice; no Ion token or paid services
- DEM requests use AWS Terrarium tiles at fixed zoom `12`
- API always returns a fixed `128 x 128` analysis grid
- UI keeps the planned `1km` to `50km` radius range
- Backend enforces a hard tile-count cap to keep hour-one performance sane
- Terrain fetch is user-triggered with a button, not automatic on every interaction
- No persistence, auth, or map annotation storage is included in this slice
