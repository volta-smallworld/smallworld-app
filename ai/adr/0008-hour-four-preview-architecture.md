# ADR 0008: Hour-Four Preview Architecture

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [ADR 0004](./0004-use-token-free-cesium-for-hour-one-map-selection.md), [ADR 0006](./0006-use-aws-terrarium-tiles-for-hour-one-dem-source.md), [hour-four plan](../plans/hour-four.md)

## Context

Hour four introduces visual previews of terrain viewpoints. The system already has two apps: a FastAPI backend that owns terrain analysis and a Next.js frontend that owns Cesium-based globe rendering. The question is which app should own preview rendering, and what level of visual fidelity the preview requires.

Rendering a preview image requires a headless browser (Playwright), a Node.js runtime, and the full set of Cesium assets (Workers, ThirdParty, Assets, Widgets) that the web app already bundles and serves. The API backend is Python and has no relationship with any of these dependencies.

## Decision Drivers

- Minimize new cross-process and cross-language complexity.
- Keep rendering dependencies close to the code that already owns them.
- Allow previews to be disabled without degrading existing terrain analysis and viewpoint search functionality.
- Provide high-fidelity terrain previews when the infrastructure supports it.

## Options Considered

- Option A: Render previews in the web app (apps/web) using Playwright and the Cesium assets it already owns.
- Option B: Render previews in the API (apps/api) by adding Node.js, Playwright, and Cesium as Python-side dependencies or via a subprocess.
- Option C: Create a dedicated third service for preview rendering.

## Decision

Two decisions are recorded here.

**Decision 1 — Preview rendering lives in the web app, not the API.**

Hour-four previews are rendered by the web app (apps/web). The renderer depends on Node.js, Playwright, and Cesium assets that are already owned by the web app. Cross-process rendering from Python would add unnecessary complexity: the API would need to shell out to Node or manage a sidecar, duplicate Cesium asset hosting, and introduce a fragile inter-process contract. None of that is justified when the web app already has everything the renderer needs.

**Decision 2 — Preview fidelity requires an optional Ion-backed terrain and imagery provider.**

High-fidelity previews require real terrain meshes and satellite imagery, which are only available through Cesium Ion (configured via `NEXT_PUBLIC_CESIUM_ION_TOKEN`). When the token is not configured, preview rendering is disabled. This does not break the rest of the product: terrain analysis, viewpoint search, and the interactive map all continue to work exactly as they do today. The Ion token is additive, not load-bearing.

## Decision Details

- The web app owns the preview-rendering pipeline end to end: scene setup, Cesium viewer instantiation, screenshot capture, and image delivery.
- The API continues to own terrain analysis, elevation grids, feature extraction, and viewpoint scoring. Nothing in this ADR changes the API's responsibilities. Existing ADRs — especially ADR 0006 (Terrarium tiles in the API) — still stand.
- The web app is not proxying or wrapping FastAPI for preview rendering. It is serving its own distinct capability.
- `NEXT_PUBLIC_CESIUM_ION_TOKEN` is the single env var that gates preview availability. When absent or empty, the preview subsystem is inert.
- Playwright is a dev/build dependency of the web app, not a runtime dependency of the API.
- The token-free Cesium globe (ADR 0004) remains the default interactive experience. Ion-backed rendering is used only for offline preview capture, not for the interactive map.

## Consequences

- Preview rendering shares the web app's deployment and does not require a separate service or sidecar.
- The API stays lean and Python-only with no Node.js, Playwright, or Cesium asset dependencies.
- Preview availability is environment-dependent: environments without an Ion token simply skip previews.
- The web app takes on a new responsibility (headless rendering), which increases its surface area but keeps all Cesium-related concerns in one place.
- There is no new inter-process or cross-language coupling between the API and the web app for preview rendering.

## Implementation Notes

- Preview rendering code should live under `apps/web/` alongside the existing Cesium configuration.
- `NEXT_PUBLIC_CESIUM_ION_TOKEN` should be documented in the web app's environment setup and checked at preview-render time; its absence should produce a clear skip rather than an error.
- Playwright should be listed as a dependency of the web app, not the API or the monorepo root.
- The interactive Cesium globe in the browser should remain token-free (per ADR 0004) regardless of whether the Ion token is configured for previews.

## Validation

- Preview rendering works when `NEXT_PUBLIC_CESIUM_ION_TOKEN` is set and Playwright is available.
- Preview rendering is cleanly disabled when the Ion token is missing, with no errors or degraded behavior in the rest of the product.
- Terrain analysis, elevation grid fetching, and viewpoint search all function identically whether or not the Ion token is configured.
- The API has no Playwright, Node.js, or Cesium asset dependencies.

## Follow-ups

- Add a future ADR if preview rendering moves to a dedicated microservice or cloud function for scalability.
- Revisit the Ion dependency if a token-free terrain and imagery source with sufficient fidelity becomes available.
- Consider caching or pre-generating previews if rendering latency becomes a user-facing concern.
