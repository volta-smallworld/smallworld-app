# Deployment Reference

Live deployment details for the Smallworld stack. Three services across two platforms.

## Services

| Service | Platform | URL | Status |
|---------|----------|-----|--------|
| Web (Next.js 15) | Vercel | https://smallworld-app-one.vercel.app | Auto-deploy on push to `main` |
| API (FastAPI) | Railway | https://smallworld-api-production.up.railway.app | Auto-deploy on push to `main` |
| MCP (FastMCP) | Railway | https://smallworld-mcp-production.up.railway.app | Auto-deploy on push to `main` |

### Internal networking (Railway)

| From | To | URL |
|------|----|-----|
| MCP | API | `http://smallworld-api.railway.internal` |
| API | MCP | `http://smallworld-mcp.railway.internal` |

## Railway Project

- **Project:** smallworld (`f7cbcdcb-51c6-472c-8ece-22087d7c79b6`)
- **Environment:** production
- **Region:** (set in Railway dashboard)

### smallworld-api

- **Service ID:** `0ee03d1c-7cbd-47bd-90d1-bc374c4ba07f`
- **Dockerfile:** `apps/api/Dockerfile` (multi-stage: Python 3.12 + CPU torch + Chromium + Node 20 + Puppeteer)
- **Start command:** `cd /app/apps/api && uvicorn smallworld_api.main:app --host 0.0.0.0 --port $PORT`
- **Health check:** `GET /healthz` (30s timeout)
- **Volume:** `smallworld-api-volume` mounted at `/data`
  - `/data/preview_artifacts` — rendered preview PNGs
  - `/data/style_artifacts` — style reference images

#### API Environment Variables

| Variable | Value | Source |
|----------|-------|--------|
| `CORS_ORIGINS` | `https://smallworld-app-one.vercel.app,http://localhost:4182,http://127.0.0.1:4182` | User-set |
| `GOOGLE_MAPS_API_KEY` | `(secret)` | User-set |
| `PREVIEW_ARTIFACTS_DIR` | `/data/preview_artifacts` | User-set |
| `PREVIEW_PUBLIC_BASE_URL` | `https://smallworld-api-production.up.railway.app` | User-set |
| `PREVIEW_RENDERER_BASE_URL` | `https://smallworld-app-one.vercel.app/render/preview` | User-set |
| `PUPPETEER_EXECUTABLE_PATH` | `/usr/bin/chromium` | User-set |
| `RENDER_SCRIPT_PATH` | `/app/apps/web/scripts/render-preview.mjs` | User-set |
| `STYLE_ARTIFACTS_DIR` | `/data/style_artifacts` | User-set |
| `RAILWAY_HEALTHCHECK_PATH` | `/healthz` | Railway |
| `RAILWAY_VOLUME_MOUNT_PATH` | `/data` | Railway |

### smallworld-mcp

- **Service ID:** `3a6d4008-6ead-4411-ba1c-b43e0e79194a`
- **Dockerfile:** `apps/api/Dockerfile.mcp` (lightweight — no Chromium/Node, delegates rendering to API)
- **Start command:** `cd /app/apps/api && python -m smallworld_api.mcp.cli --transport http --host 0.0.0.0 --port $PORT`
- **No volume** — delegates artifact storage to API service

#### MCP Environment Variables

| Variable | Value | Source |
|----------|-------|--------|
| `API_INTERNAL_URL` | `http://smallworld-api.railway.internal` | User-set |
| `PREVIEW_PUBLIC_BASE_URL` | `https://smallworld-api-production.up.railway.app` | User-set |

## Vercel Project

- **Project:** smallworld-app
- **Framework:** Next.js (auto-detected)
- **Root directory:** `apps/web`
- **Build command:** `pnpm run build`
- **Config:** `apps/web/vercel.json`

### Web Environment Variables

| Variable | Value | Exposure |
|----------|-------|----------|
| `NEXT_PUBLIC_API_BASE_URL` | `https://smallworld-api-production.up.railway.app` | Browser |
| `MCP_SERVER_URL` | `https://smallworld-mcp-production.up.railway.app/mcp` | Server-only |
| `DEEPSEEK_API_KEY` | `(secret)` | Server-only |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | `(secret, optional)` | Browser |
| `NEXT_PUBLIC_CESIUM_ION_TOKEN` | `(secret, optional)` | Browser |

## Data Flow

```
Browser
  |
  v
Vercel (Next.js)
  |-- NEXT_PUBLIC_API_BASE_URL --> Railway API (REST)
  |-- MCP_SERVER_URL ------------> Railway MCP (JSON-RPC)
  |
  ^  (Puppeteer navigates to /render/preview)
  |
Railway API
  |-- PREVIEW_RENDERER_BASE_URL -> Vercel /render/preview page
  |
Railway MCP
  |-- API_INTERNAL_URL ----------> Railway API (internal network)
```

## Deployment Config Files

| File | Purpose |
|------|---------|
| `apps/api/Dockerfile` | API image: Python + torch (CPU) + Chromium + Node + Puppeteer |
| `apps/api/Dockerfile.mcp` | MCP image: Python only (no Chromium), delegates rendering |
| `apps/web/vercel.json` | Vercel framework preset |
| `railway.toml` | Railway deploy config (restart policy, health check) |
| `.dockerignore` | Excludes unnecessary files from Docker build context |

## Docker Build

Both Dockerfiles use the **repo root** as build context (not `apps/api/`), because the API image needs `apps/web/scripts/render-preview.mjs`.

```bash
# Build API image locally
docker build -f apps/api/Dockerfile -t smallworld-api .

# Build MCP image locally
docker build -f apps/api/Dockerfile.mcp -t smallworld-mcp .
```

### Layer caching strategy

Stage 1 (`python-deps`) installs all Python deps including torch. This ~1.5GB layer only rebuilds when `pyproject.toml` or `uv.lock` change. Source code changes only invalidate the final COPY layers, keeping most deploys fast.

GPU torch is replaced with CPU-only torch (`--index-url https://download.pytorch.org/whl/cpu`) and CUDA/nvidia packages are stripped to save ~1.5GB.

## Verification

```bash
# API health check
curl https://smallworld-api-production.up.railway.app/healthz

# Terrain request
curl -X POST https://smallworld-api-production.up.railway.app/api/v1/terrain/elevation-grid \
  -H "Content-Type: application/json" \
  -d '{"center":{"lat":47.6,"lng":-122.3},"radius_km":5}'

# Web app
open https://smallworld-app-one.vercel.app
```

## Adding Environment Variables

```bash
# Railway (API)
railway variables set KEY=value --service smallworld-api

# Railway (MCP)
railway variables set KEY=value --service smallworld-mcp

# Vercel — use dashboard or:
vercel env add VARIABLE_NAME production
```
