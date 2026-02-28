# ADR 0002: Standardize Web Stack on Next.js App Router

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [hour-one plan](../plans/hour-one.md), [ADR 0001](./0001-adopt-monorepo-app-structure.md)

## Context

Hour one needed a frontend stack that could be scaffolded quickly, handle a browser-only 3D map, and still provide a clean structure for future server and client responsibilities. The project also needed type safety around a terrain API contract that would evolve quickly.

## Decision Drivers

- Optimize for fast product iteration and strong default DX.
- Keep the frontend aligned with modern Next.js conventions rather than older routing patterns.
- Enforce type safety around API payloads and UI state from the start.

## Options Considered

- Next.js App Router with TypeScript.
- Next.js Pages Router with TypeScript.
- A lighter frontend scaffold with no framework-level routing commitment yet.

## Decision

The web application will use Next.js App Router with TypeScript, and Cesium integration will be isolated to client-only code paths.

## Decision Details

- App Router is preferred over Pages Router because it is the current Next.js direction and gives the repo a modern default shape.
- TypeScript is required from the start for request and response typing, map selection state, and safer UI evolution.
- Cesium must be isolated to client-only components because it depends on browser APIs and should not participate in server rendering.
- The hour-one frontend surface centers on:
  - `src/app/` for App Router entrypoints.
  - `src/components/` for UI and Cesium components.
  - `src/lib/` for API and Cesium helpers.
  - `src/types/` for terrain contract types.

## Consequences

- The frontend gets a modern structure that scales better than a legacy pages layout.
- TypeScript reduces drift between the documented API contract and the UI.
- Cesium requires explicit client-only boundaries, which adds a little setup complexity but avoids brittle SSR failures.

## Implementation Notes

- The primary route should live under `apps/web/src/app/`.
- Cesium components should be imported through client-only boundaries such as dynamic imports with SSR disabled.
- Shared frontend types should mirror the backend terrain response contract closely enough to catch drift during development.

## Validation

- `apps/web` is configured as a Next.js TypeScript app.
- The main route is implemented under the App Router directory structure.
- Cesium usage is contained in browser-only components rather than imported directly into server-rendered modules.

## Follow-ups

- Add an ADR if the frontend later requires shared packages, server actions, or a different rendering strategy for map-adjacent flows.
- Revisit the type-sharing approach if runtime validation or generated client types become necessary.
