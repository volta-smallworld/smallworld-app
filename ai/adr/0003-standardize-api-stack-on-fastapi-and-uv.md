# ADR 0003: Standardize API Stack on FastAPI and uv

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [hour-one plan](../plans/hour-one.md), [ADR 0001](./0001-adopt-monorepo-app-structure.md)

## Context

The backend needed to support numerical terrain processing, clean request validation, and a fast path to exposing a JSON API. The repo also needed a Python workflow that was straightforward to set up locally without mixing language-specific toolchains at the root.

## Decision Drivers

- Match the terrain-processing roadmap to the Python scientific ecosystem.
- Keep API development fast and well-typed.
- Make local setup and dependency management explicit and repeatable.

## Options Considered

- FastAPI on Python 3.12 with `uv`.
- A JavaScript or TypeScript backend colocated with the frontend stack.
- Delaying the backend entirely and relying on mocked terrain responses.

## Decision

The hour-one backend will use FastAPI on Python 3.12, manage dependencies with `uv`, and include CORS as part of the baseline service setup.

## Decision Details

- FastAPI is chosen because it provides fast routing, schema-driven request validation, and a clean match for Pydantic-based API contracts.
- Python 3.12 is the default runtime because it aligns with the local toolchain and supports the numerical processing path planned for later hours.
- `uv` is the dependency and environment manager for `apps/api`.
- CORS is not optional in hour one because the web app and API run as separate local processes and must interoperate immediately.
- Baseline API behavior includes:
  - `GET /healthz` for local readiness.
  - versioned terrain routes under `/api/v1/terrain`.

## Consequences

- The backend is well positioned for NumPy-heavy terrain processing and future ML integrations.
- Local setup remains explicit instead of hidden behind a more opaque global environment.
- The team accepts a split-language stack, which adds some context switching but keeps each app on a toolchain suited to its job.

## Implementation Notes

- `apps/api/pyproject.toml` is the source of truth for backend dependencies.
- `apps/api/src/smallworld_api/config.py` should hold environment-backed settings such as `CORS_ORIGINS`, `TERRARIUM_TILE_URL_TEMPLATE`, `DEFAULT_TERRARIUM_ZOOM`, and `MAX_TILES_PER_REQUEST`.
- `apps/api/src/smallworld_api/main.py` should register CORS middleware and expose the health endpoint.

## Validation

- The API runs on Python 3.12 with dependencies managed through `uv`.
- FastAPI serves `GET /healthz` successfully.
- Cross-origin requests from the local web app succeed because allowed origins are configured.

## Follow-ups

- Add a new ADR if API versioning, deployment packaging, or Python environment management changes materially.
- Revisit CORS scope when the app moves beyond local development or introduces authenticated traffic.
