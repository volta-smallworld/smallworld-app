# ADR 0001: Adopt Monorepo App Structure

- Status: Accepted
- Date: 2026-02-28
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [hour-one plan](../plans/hour-one.md)

## Context

The repository started as a greenfield project with only planning material and no established application structure. Hour one needed a repo layout that could support a web UI, a Python API, and shared root-level development documentation without over-investing in build orchestration before the product shape was proven.

## Decision Drivers

- Keep the web and API codebases clearly separated from the beginning.
- Preserve fast local iteration for a short hackathon-style implementation window.
- Avoid premature tooling complexity while still leaving room for future growth.

## Options Considered

- Two-app monorepo with `apps/web` and `apps/api`.
- Single root application with mixed frontend and backend assets.
- Frontend-only initial repo with the API deferred to a later phase.

## Decision

The repository will use a two-app monorepo layout with `apps/web` for the Next.js frontend and `apps/api` for the FastAPI backend, while keeping shared scripts, docs, and workspace configuration at the repo root.

## Decision Details

- The canonical top-level layout is:
  - `apps/web` for the frontend runtime and UI code.
  - `apps/api` for the Python API runtime and terrain processing logic.
  - root files for shared workspace metadata such as `package.json`, `pnpm-workspace.yaml`, `.gitignore`, and `README.md`.
  - `ai/` for planning and architecture records.
- Turbo is intentionally deferred for hour one because the repo only needs simple root scripts and separate local processes.
- Ownership boundaries are explicit:
  - web-specific UI, map integration, and API client code stay in `apps/web`.
  - API routes, models, and terrain services stay in `apps/api`.
  - cross-cutting decisions are documented in ADRs rather than hidden in directory sprawl.

## Consequences

- The repo is easier to reason about than a mixed single-root application.
- Web and API tooling can evolve independently without immediate build-system coupling.
- Root-level developer ergonomics stay simple, but cross-app automation remains manual until a future orchestration layer is introduced.

## Implementation Notes

- Root scripts should delegate to the relevant app rather than flattening all tools into one runtime.
- The hour-one implementation should keep the Python environment isolated inside `apps/api` and the Node workspace centered on `apps/web`.
- Future shared packages can be introduced later if real reuse emerges, but they are not required for the initial slice.

## Validation

- The repository contains both `apps/web` and `apps/api`.
- Root-level documentation and workspace files exist alongside the app directories.
- No decision in hour one depends on Turbo, Nx, or another orchestration layer.

## Follow-ups

- Add a new ADR if the repo grows enough to justify Turbo, shared packages, or a broader workspace orchestration strategy.
- Revisit ownership boundaries if a shared domain model becomes substantial across both apps.
