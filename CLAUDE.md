# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

**Always use the Makefile** for starting, stopping, and managing the dev stack. If a Makefile target doesn't exist for what you need, add one. Use `/usr/bin/make` (the shell has a `make` autoload function that shadows it).

```bash
# Dev stack (preferred — manages all services with PID tracking)
/usr/bin/make up                # Start API (:8080), MCP (:8001), Web (:3000) in background
/usr/bin/make down              # Stop all services
/usr/bin/make restart           # Stop + start all services
/usr/bin/make status            # Show which services are running
/usr/bin/make logs              # Tail all log files (.logs/)

# Individual services
/usr/bin/make up-api            # Start API only
/usr/bin/make up-mcp            # Start MCP only
/usr/bin/make up-web            # Start Web only
/usr/bin/make down-api          # Stop API only
/usr/bin/make down-mcp          # Stop MCP only
/usr/bin/make down-web          # Stop Web only

# Install dependencies
pnpm install                    # Web (from repo root)
cd apps/api && uv sync          # API

# Testing
pnpm test:api                   # All backend tests
cd apps/api && uv run pytest tests/test_tile_math.py -k test_bounds_shape  # Single test

# Linting
pnpm lint:web                   # ESLint + TypeScript checks
```

## Architecture

Monorepo with two independent apps — no shared packages or cross-app imports. Types matching the API contract are duplicated in each app by design.

**`apps/api`** — FastAPI (Python 3.12, managed by `uv`)
- `src/smallworld_api/main.py` — App creation, CORS middleware, router mount
- `src/smallworld_api/config.py` — `pydantic-settings` config (CORS origins, Terrarium URL, zoom, tile cap)
- `src/smallworld_api/routes/terrain.py` — `POST /api/v1/terrain/elevation-grid`
- `src/smallworld_api/services/tiles.py` — Pure geo math: center+radius→bounds, bounds→slippy-map tile range, tile bounds lookup
- `src/smallworld_api/services/terrarium.py` — Full pipeline: fetch AWS Terrarium PNGs via httpx, decode RGB→elevation (`R*256+G+B/256-32768`), stitch tiles into mosaic, crop to bounds, resample to fixed 128×128 grid, compute stats
- `src/smallworld_api/models/terrain.py` — Pydantic request/response models with validation (lat ±90, lng ±180, radius 1–50km)

**`apps/web`** — Next.js 15 App Router (TypeScript, pnpm)
- `src/app/page.tsx` — Client component orchestrating state (center, radius, fetch state, result/error)
- `src/components/cesium-map.tsx` — Token-free Cesium globe with click-to-select and radius ellipse overlay. Uses `ImageryLayer` with `OpenStreetMapImageryProvider`, no Ion token.
- `src/components/control-panel.tsx` — Lat/lng display, radius slider (1–50km), fetch button
- `src/components/terrain-result-panel.tsx` — Displays elevation stats, grid info, bounds, tile count
- `src/lib/api.ts` — `fetchElevationGrid()` calling the FastAPI backend
- `src/lib/cesium.ts` — Sets `window.CESIUM_BASE_URL`, disables Ion token
- `next.config.mjs` — Webpack plugin copies Cesium assets (Workers, ThirdParty, Assets, Widgets) to `public/cesium/`

## Key Constraints

- **Cesium assets** must exist at `public/cesium/` — the webpack copy plugin handles this during build, but the first `next dev` may need a build or page refresh
- **CORS** is configured for `localhost:3000` and `127.0.0.1:3000` only — update `config.py` for other origins
- **Tile cap**: max 36 tiles per request (configurable via `MAX_TILES_PER_REQUEST` env var) — returns 422 if exceeded
- **Grid size**: always 128×128, hardcoded in `terrarium.py` as `GRID_SIZE`
- **Zoom level**: default 12, configurable via `DEFAULT_TERRARIUM_ZOOM` env var
- Web reads `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8080`); API reads `.env` via pydantic-settings

## Testing Patterns

Backend tests use `FastAPI.TestClient` with `unittest.mock.patch` to mock the service layer. Route tests mock `get_elevation_grid` as an `AsyncMock`. Pure function tests (decode, tile math) run without mocks. Pytest asyncio mode is set to `auto` in `pyproject.toml`.

## Documentation

Architecture decisions are recorded in `ai/adr/` following the template in `ai/adr/_template.md`. Plans live in `ai/plans/`.
