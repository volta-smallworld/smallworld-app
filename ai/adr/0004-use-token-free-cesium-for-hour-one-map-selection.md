# ADR 0004: Use Token-Free Cesium for Hour-One Map Selection

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [hour-one plan](../plans/hour-one.md), [ADR 0002](./0002-standardize-web-stack-on-nextjs-app-router.md)

## Context

The first user-visible slice needed a real globe interaction quickly, but hour one could not afford to spend time on external token setup or more ambitious terrain viewer polish. The map also needed a simple interaction contract that matched the first backend request shape.

## Decision Drivers

- Deliver a working globe-based selection flow in hour one.
- Reduce dependency on external account setup and secrets.
- Keep the user interaction model obvious and low risk.

## Options Considered

- Token-free Cesium globe with click-to-select center and slider-based radius control.
- Full Cesium terrain setup with token-backed services and more advanced viewer configuration.
- A placeholder or non-Cesium map for the first slice.

## Decision

Hour one will use a token-free Cesium globe with click-to-select center, a radius slider, a visible center marker, a visible radius ellipse, and a user-triggered terrain fetch action.

## Decision Details

- Cesium Ion and token-dependent terrain services are intentionally avoided in hour one.
- The initial globe should use a token-free base such as an ellipsoid terrain provider with open imagery.
- The map selection contract is:
  - one selected center point expressed as latitude and longitude.
  - one selected radius in meters.
  - one visible marker at the selected center.
  - one visible ellipse representing the selected radius.
- The first UX is click-plus-slider rather than drag-to-size because it is simpler to implement and easier to validate.
- Terrain fetches are explicit user actions, not automatic side effects of every map change.
- Drag-only radius interaction is explicitly rejected for hour one.

## Consequences

- The first slice is easier to demo and run locally because there is no token or secret dependency.
- The map experience is intentionally conservative rather than highly polished.
- The project defers real 3D terrain rendering concerns to later iterations, which is acceptable because hour one is about input collection and API wiring.

## Implementation Notes

- Cesium should be configured with a token-free globe setup in `apps/web/src/lib/cesium.ts`.
- The page-level state should carry selected center and selected radius separately.
- The main page and map component should keep the marker and ellipse in sync with the current selection.
- A fetch button in the control panel should be the only trigger for the terrain API call.

## Validation

- The web app renders a Cesium globe without requiring an Ion token.
- Clicking the globe updates the selected center.
- Adjusting the slider updates the displayed radius and visible ellipse.
- Terrain requests are fired only when the user explicitly submits the request.

## Follow-ups

- Add a future ADR if the product moves to true terrain-backed Cesium rendering, drag-to-size interactions, or richer map overlays.
- Revisit the interaction model once the terrain scoring workflow is mature enough to justify more dynamic updates.
