# Architecture Decision Records

This directory is the canonical home for Architecture Decision Records in this repository. The location is intentionally `ai/adr/` for this project, even though `docs/adr/` is more common elsewhere.

## Conventions

- Scope: capture durable architectural decisions, not every tactical implementation choice.
- Granularity: one ADR per major decision area; smaller defaults belong in the closest ADR as sub-decisions.
- Naming: sequential numbers with kebab-case slugs, for example `0001-sample-decision.md`.
- Status values:
  - `Proposed`
  - `Accepted`
  - `Superseded`
  - `Deprecated`
  - `Rejected`
- Immutability: accepted ADRs are historical records; create a new ADR to change direction instead of rewriting the old one.
- Superseding: when an ADR is replaced, update the older ADR status to `Superseded`, add a pointer to the newer ADR, and link back from the new ADR.
- References: each ADR should link to the relevant source material in [plan.md](../../plan.md) and any related ADRs or implementation plans.

## Required Structure

Every ADR in this directory should follow the shared template in [_template.md](./_template.md) and use the sections in this order:

1. Title and metadata
2. Context
3. Decision Drivers
4. Options Considered
5. Decision
6. Decision Details
7. Consequences
8. Implementation Notes
9. Validation
10. Follow-ups

## Index

| ADR | Status | Title | Summary |
| --- | --- | --- | --- |
| [0001](./0001-adopt-monorepo-app-structure.md) | Accepted | Adopt Monorepo App Structure | Use a two-app monorepo with `apps/web` and `apps/api`, and defer Turbo in hour one. |
| [0002](./0002-standardize-web-stack-on-nextjs-app-router.md) | Accepted | Standardize Web Stack on Next.js App Router | Build the frontend on Next.js App Router with TypeScript and client-only Cesium integration. |
| [0003](./0003-standardize-api-stack-on-fastapi-and-uv.md) | Accepted | Standardize API Stack on FastAPI and uv | Use FastAPI, Python 3.12, `uv`, and baseline CORS for the hour-one backend. |
| [0004](./0004-use-token-free-cesium-for-hour-one-map-selection.md) | Accepted | Use Token-Free Cesium for Hour-One Map Selection | Ship a token-free Cesium globe with click-to-select center, radius slider, and explicit fetch action. |
| [0005](./0005-use-direct-web-to-api-communication.md) | Accepted | Use Direct Web-to-API Communication | Have the web app call FastAPI directly through `NEXT_PUBLIC_API_BASE_URL` without a Next proxy. |
| [0006](./0006-use-aws-terrarium-tiles-for-hour-one-dem-source.md) | Accepted | Use AWS Terrarium Tiles for Hour-One DEM Source | Use AWS Terrarium at a fixed initial zoom with backend guardrails on tile fan-out. |
| [0007](./0007-standardize-the-hour-one-elevation-grid-contract.md) | Accepted | Standardize the Hour-One Elevation Grid Contract | Expose `POST /api/v1/terrain/elevation-grid` with a center-plus-radius request and fixed-size grid response. |
| [0008](./0008-hour-four-preview-architecture.md) | Superseded by 0010 | Hour Four Preview Architecture | Preview rendering pipeline with Puppeteer-based headless Cesium, enhancement, and artifact storage. |
| [0009](./0009-precise-point-elevation-and-agl-camera-safety.md) | Accepted | Precise Point Elevation and AGL Camera Safety | Three-layer AGL enforcement with raw-tile point sampler to prevent camera-inside-mountain failures. |
| [0010](./0010-delegate-web-previews-to-api-pipeline.md) | Accepted | Delegate Web Previews to API Pipeline | Web preview route delegates to API pipeline for unified rendering with provider fallback. |
