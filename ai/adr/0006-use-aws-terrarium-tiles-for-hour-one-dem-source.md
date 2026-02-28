# ADR 0006: Use AWS Terrarium Tiles for Hour-One DEM Source

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [hour-one plan](../plans/hour-one.md), [ADR 0003](./0003-standardize-api-stack-on-fastapi-and-uv.md), [ADR 0007](./0007-standardize-the-hour-one-elevation-grid-contract.md)

## Context

Hour one required a globally available elevation source that could be fetched programmatically without spending time on access approval, credentials, or bulk dataset ingestion. The backend also needed predictable behavior around tile fan-out so a large search radius would not explode into an unbounded remote fetch.

## Decision Drivers

- Use a DEM source that is fast to integrate and does not require API key setup.
- Keep the initial backend implementation tractable within the hour-one scope.
- Bound request cost and failure modes before terrain analysis gets more sophisticated.

## Options Considered

- AWS Terrarium tiles fetched on demand by the FastAPI backend.
- A different DEM source requiring more credentials, preprocessing, or ingestion work.
- Mock terrain data for hour one with the real DEM source deferred.

## Decision

The hour-one backend will fetch DEM data from AWS Terrarium tiles, decode Terrarium RGB values into elevation meters, and enforce backend guardrails on tile coverage at a fixed initial zoom.

## Decision Details

- AWS Terrarium is the upstream DEM source for the first slice.
- The fixed initial zoom defaults to `12`, which is acceptable for hour one because the goal is stable end-to-end data flow rather than adaptive multi-resolution optimization.
- The Terrarium decode formula is part of the contract:
  - `elevation_m = (R * 256 + G + B / 256) - 32768`
- The backend is responsible for:
  - converting center-plus-radius requests into geographic bounds.
  - converting bounds into slippy-map tile coverage.
  - fetching and decoding the required Terrarium tiles.
  - stitching, cropping, and resampling the result into the fixed analysis grid.
- Backend guardrails are required:
  - `MAX_TILES_PER_REQUEST` limits tile fan-out.
  - oversized requests should be rejected with a validation-style error rather than attempting an expensive fetch.

## Consequences

- The project gets a zero-credential DEM pipeline quickly.
- The API behavior is predictable enough for local development and tests.
- Fixed zoom keeps the first implementation simple, but it is not the final answer for all radii or precision needs.
- The backend now owns remote data fetch reliability and must translate upstream failures cleanly.

## Implementation Notes

- `apps/api/src/smallworld_api/config.py` should define:
  - `TERRARIUM_TILE_URL_TEMPLATE`
  - `DEFAULT_TERRARIUM_ZOOM`
  - `MAX_TILES_PER_REQUEST`
- `apps/api/src/smallworld_api/services/tiles.py` should hold geographic and slippy-map math.
- `apps/api/src/smallworld_api/services/terrarium.py` should own fetch, decode, stitch, crop, resample, and stats generation.

## Validation

- The backend can fetch Terrarium PNGs and decode them into expected elevation values.
- Requests at the default zoom reject oversized tile coverage before remote fan-out begins.
- The documented env var names and decode behavior match the running code and tests.

## Follow-ups

- Add a future ADR if the product introduces adaptive zooming, multi-source DEM fallbacks, caching, or precomputed terrain stores.
- Revisit guardrails once real user behavior and performance data exist.
