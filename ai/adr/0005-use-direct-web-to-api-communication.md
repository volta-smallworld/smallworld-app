# ADR 0005: Use Direct Web-to-API Communication

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [hour-one plan](../plans/hour-one.md), [ADR 0003](./0003-standardize-api-stack-on-fastapi-and-uv.md), [ADR 0007](./0007-standardize-the-hour-one-elevation-grid-contract.md)

## Context

The web app and API were intentionally split into separate processes in hour one. The project needed a simple integration seam that kept the frontend and backend independently runnable without adding a proxy layer or duplicating request logic in both stacks.

## Decision Drivers

- Keep the first cross-app integration path simple and explicit.
- Avoid unnecessary routing layers in a greenfield repo.
- Make local development and environment configuration obvious.

## Options Considered

- Direct browser-to-FastAPI requests using an environment-configured base URL.
- A Next.js proxy route or route handler in front of FastAPI.
- Mock-only frontend integration with the real API deferred.

## Decision

The Next.js frontend will call the FastAPI backend directly through `NEXT_PUBLIC_API_BASE_URL`, and the API will allow those browser requests through configured `CORS_ORIGINS`.

## Decision Details

- `NEXT_PUBLIC_API_BASE_URL` is the source-of-truth integration seam for the web app.
- `CORS_ORIGINS` is the source-of-truth server setting that allows the frontend origins to call the API.
- The hour-one architecture explicitly excludes a Next.js proxy layer, BFF route handler, or shared origin abstraction.
- Direct communication is the default for both local development and the first working demo because it minimizes moving parts.

## Consequences

- The integration path is easy to understand and debug because the browser talks directly to the API.
- Frontend and backend deployment topologies remain decoupled.
- CORS configuration becomes part of the product contract and must be maintained carefully.
- If the project later needs auth, request shaping, or secret server-side mediation, another architecture step will be required.

## Implementation Notes

- `apps/web/src/lib/api.ts` should read `NEXT_PUBLIC_API_BASE_URL` and call `POST /api/v1/terrain/elevation-grid` directly.
- `apps/api/src/smallworld_api/config.py` should define `cors_origins`.
- `apps/api/src/smallworld_api/main.py` should register FastAPI CORS middleware with those origins.
- No Next.js route handler should proxy terrain requests in hour one.

## Validation

- The frontend can successfully call the API from a different local origin.
- The web code has a single direct API client path rather than a proxy hop.
- The env var names `NEXT_PUBLIC_API_BASE_URL` and `CORS_ORIGINS` appear consistently in docs and implementation.

## Follow-ups

- Add a new ADR if the project later introduces a BFF layer, authenticated request mediation, or same-origin deployment constraints.
- Revisit this decision if browser-to-API communication becomes operationally awkward in production.
