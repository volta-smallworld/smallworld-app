# Smallworld

**The algorithmic photography angle finder.**

No tool today algorithmically analyzes terrain to find optimal photography viewpoints using composition principles. Every technical component exists independently — DEM analysis, inverse projection, fractal geometry, composition theory, photorealistic rendering. The integration is the innovation.

## What it does

A photographer or drone pilot picks a location and search radius on a 3D globe. Smallworld fetches elevation data, extracts terrain features (peaks, ridgelines, cliffs, water channels), groups them into photographable scenes, and **computes** camera positions that satisfy composition rules — rule of thirds, golden ratio, leading lines, symmetry — by construction, not by searching.

The key insight: composition rules are geometric constraints. If you know where terrain features are in 3D and where you want them in the 2D frame, the camera position is a solvable equation. This turns a 10-billion-viewpoint brute-force search into ~500 deterministic candidates, all compositionally valid, scored by proxy beauty metrics derived from the DEM itself (viewshed richness, skyline fractal dimension, prospect-refuge balance, depth layering, mystery).

Top candidates are rendered as photorealistic previews with GPS coordinates, altitude, and heading — ready to navigate to and shoot.

## How it works

```
Select area on globe
  → Fetch DEM tiles (AWS Terrarium, free, no API key)
  → Compute terrain derivatives (slope, curvature, relief)
  → Extract features (peaks by prominence, ridges by inverted hydrology,
    cliffs by curvature, water by flow accumulation)
  → Group features into scenes (peak+lake, ridge+peak, cliff+valley)
  → For each scene × composition template:
      solve camera pose via inverse projection (not search)
  → Validate physics (underground? occluded? out of bounds?)
  → Score by DEM-only beauty metrics (no rendering needed)
  → Render top candidates via CesiumJS + Google 3D Tiles
  → Enhance with Gemini image generation (photorealistic sky, lighting)
  → Return ranked viewpoints with coordinates and preview images
```

## Architecture

Monorepo with three independent services:

| Service | Stack | Port | Purpose |
|---------|-------|------|---------|
| **API** | FastAPI, Python 3.12, uv | 8080 | Terrain analysis, feature extraction, viewpoint computation, preview orchestration |
| **MCP** | FastMCP (Python) | 8001 | Model Context Protocol server exposing terrain/viewpoint/preview tools for AI agents |
| **Web** | Next.js 15, TypeScript, CesiumJS | 3000 | Interactive globe, chat interface, preview display |

The MCP server enables an agent workflow: `terrain_analyze_area` → `terrain_find_viewpoints` → `preview_render_pose`. The web app includes a chat interface backed by Claude that uses these MCP tools to analyze terrain and render previews conversationally.

### Key algorithms

- **Inverse PnP camera solving** — Given 3D feature positions and desired 2D screen placements from a composition template, solve for camera pose. Pitch from horizon ratio, position + yaw from constrained least-squares.
- **Ridgeline fractal distance** — Compute the viewing distance that makes a ridgeline's silhouette have fractal dimension D ≈ 1.3 (the empirically preferred complexity). Pure DEM math, no rendering.
- **Proxy beauty scoring** — Seven DEM-only metrics: viewshed richness, terrain entropy, skyline fractal score, prospect-refuge balance, depth layering, mystery (hidden-but-promising terrain), water visibility.
- **Preview enhancement** — Gemini image generation adds photorealistic sky, lighting, and texture to CesiumJS terrain renders while preserving terrain fidelity via constrained prompting.

## Prerequisites

- [Node.js](https://nodejs.org/) 20+
- [pnpm](https://pnpm.io/) 9+
- [Python](https://www.python.org/) 3.12+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
pnpm install          # Web dependencies
cd apps/api && uv sync  # API dependencies
```

Copy `.env.example` to `.env` and fill in API keys (Gemini for enhancement, Google Maps for 3D tiles). The terrain pipeline works without any keys — enhancement and 3D rendering are optional.

## Agent Skills (Codex + Claude Code)

This repo includes local skills under `skills/`:
- `skills/github-project-manager`
- `skills/smallworld-project-ops`

Codex:
- To make these appear in the Codex skill picker, install/symlink them into `~/.codex/skills`.
- Example:

```bash
mkdir -p ~/.codex/skills
ln -sfn /Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/skills/smallworld-project-ops ~/.codex/skills/smallworld-project-ops
ln -sfn /Users/taylordawson/code/src/github.com/volta-smallworld/smallworld-app/skills/github-project-manager ~/.codex/skills/github-project-manager
```

- Restart Codex after installing so the skills are re-indexed.

Claude Code:
- Use the repo-local skill docs directly (for example: `skills/smallworld-project-ops/SKILL.md`).
- Claude Code does not require Codex global skill installation for repo-scoped instructions.

## Running locally

Use the Makefile to manage all services:

```bash
make up       # Start API (:8080), MCP (:8001), Web (:3000) in background
make down     # Stop all services
make status   # Show which services are running
make logs     # Tail all log files
make restart  # Stop + start
```

Or start individual services:

```bash
make up-api   # API only
make up-mcp   # MCP server only
make up-web   # Web only
```

## Testing

```bash
pnpm test:api   # All backend tests
pnpm lint:web   # ESLint + TypeScript checks
```
