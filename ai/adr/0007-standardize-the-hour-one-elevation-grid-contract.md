# ADR 0007: Standardize the Hour-One Elevation Grid Contract

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [hour-one plan](../plans/hour-one.md), [ADR 0005](./0005-use-direct-web-to-api-communication.md), [ADR 0006](./0006-use-aws-terrarium-tiles-for-hour-one-dem-source.md)

## Context

Hour one needed a stable public API contract that matched the map selection flow and remained useful for later terrain analysis phases. The project had to choose between a minimal but strategically weak point-sample response and a fuller bounded-grid contract that could feed the next stages of analysis.

## Decision Drivers

- Preserve a useful terrain-analysis interface beyond the first demo.
- Keep request and response shapes stable enough for both frontend typing and backend tests.
- Bound response size while still representing the selected radius meaningfully.

## Options Considered

- `POST /api/v1/terrain/elevation-grid` with a center-plus-radius request and fixed-size bounded grid response.
- A point-sample-only terrain endpoint.
- A raw stitched tile mosaic returned directly to the frontend.

## Decision

The hour-one terrain API will expose `POST /api/v1/terrain/elevation-grid`, accept a center point plus radius in meters, and return a bounded fixed-size elevation grid with the metadata needed for downstream analysis and UI display.

## Decision Details

- Request shape:
  - `center.lat`
  - `center.lng`
  - `radiusMeters`
- Validation rules:
  - `lat` must be between `-90` and `90`.
  - `lng` must be between `-180` and `180`.
  - `radiusMeters` must be between `1000` and `50000`.
  - oversized tile coverage should be rejected by the backend with `422`.
- Response shape must include:
  - request echo metadata including `center`, `radiusMeters`, and `zoomUsed`.
  - `bounds`
  - `grid`
  - `tiles`
  - `stats`
  - `source`
- The bounded grid is fixed-size rather than raw-native-size so payload shape is stable.
- Point samples are explicitly rejected because they do not represent the selected area adequately and do not support the next terrain-analysis phase.
- Raw stitched mosaics are explicitly rejected because they create highly variable payload sizes and leak backend implementation detail into the public contract.

## Consequences

- The frontend can render stable debug and results panels without negotiating variable response shapes.
- Later analysis stages can build on a spatially meaningful grid instead of replacing a throwaway contract.
- The backend carries the complexity of resampling and metadata generation rather than offloading it to the client.

## Implementation Notes

- `apps/api/src/smallworld_api/models/terrain.py` should define the request and response models.
- `apps/api/src/smallworld_api/routes/terrain.py` should expose the endpoint and translate backend failures into `422` and `502` responses where appropriate.
- `apps/web/src/types/terrain.ts` should mirror the public contract for UI and client use.
- The grid metadata should include shape, approximate resolution, tile references, elevation stats, source, and zoom used.

## Validation

- `POST /api/v1/terrain/elevation-grid` accepts the documented request body and returns the documented top-level fields.
- The response always represents a bounded fixed-size grid rather than sparse point samples or a raw tile mosaic.
- Radius validation and oversized-request rejection match the documented `1km` to `50km` bounds and backend guardrails.
- Web and API type definitions stay aligned with the same contract fields.

## Follow-ups

- Add a new ADR if the terrain contract later needs streaming responses, binary transport, multi-resolution outputs, or richer analysis metadata.
- Revisit the fixed grid size once later phases provide real evidence that a different resolution contract is needed.
