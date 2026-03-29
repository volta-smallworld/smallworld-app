# ADR 0010: Delegate Web Previews to API Pipeline

- Status: Accepted
- Date: 2026-03-06
- Deciders: smallworld maintainers
- Related: [plan.md](../../plan.md), [ADR 0008: Hour Four Preview Architecture](./0008-hour-four-preview-architecture.md)

## Context

The web app's viewpoint preview pipeline used a local Playwright renderer invoked from the Next.js route handler. Meanwhile, the API has a robust preview pipeline with provider fallback (google_3d -> ion -> osm), composition verification, enhancement, and artifact storage. Maintaining two separate rendering paths creates duplication, inconsistent behavior, and makes it harder to add features (like fallback) in both places.

The local renderer was serial (queue-based), used an in-memory cache with no provider fallback, and had no diagnostics. Bugs in the web renderer would not be caught by API tests and vice versa.

## Decision Drivers

- Single rendering path reduces maintenance burden and bug surface area
- API pipeline already has provider fallback, enhancement, composition verification
- Preview diagnostics and monitoring are easier to centralize in one place
- Web route handler should be a thin proxy, not a rendering engine

## Options Considered

- Option A: Keep dual rendering paths, add fallback to web renderer independently.
- Option B: Delegate web previews to the API pipeline via HTTP.
- Option C: Extract shared rendering library used by both web and API.

## Decision

Delegate web previews to the API pipeline (Option B). The Next.js route handler at `/api/viewpoint-previews` now forwards render requests to `POST /api/v1/previews/render` on the API, fetches the resulting artifact, caches it locally, and returns the image to the client.

## Decision Details

- The web route maps `CameraInput` fields to the API's `CameraPoseInput` schema
- Minimal scene/composition defaults are supplied: `scene.center` = camera position, `radiusMeters` = 5000, `composition.targetTemplate` = "custom", `enhancement.enabled` = false
- API error codes (503, 504, 502) are mapped through to the web response
- Network failures to the API produce a 502 response
- The local Playwright renderer file is kept but marked `@deprecated`
- The in-memory preview cache in the web app continues to operate, caching the delegated response bytes
- A new `GET /api/v1/previews/capabilities` endpoint exposes provider state; the web capabilities route proxies to it with local fallback

## Consequences

- Single rendering path: all preview fixes and improvements in the API benefit web previews automatically
- API dependency: web previews now require the API to be running; previously they only needed Playwright
- Provider fallback: web previews now benefit from the API's google_3d -> ion -> osm chain
- Structured logging: the web route emits JSON log events for request, cache hit, render success, and render error
- Diagnostics: error messages from the API (including `detail` fields) are surfaced in the gallery UI

## Implementation Notes

- `apps/web/src/app/api/viewpoint-previews/route.ts` — delegation to `${API_BASE_URL}/api/v1/previews/render`
- `apps/web/src/app/api/viewpoint-previews/capabilities/route.ts` — proxies to `GET /api/v1/previews/capabilities`
- `apps/api/src/smallworld_api/routes/previews.py` — new `GET /capabilities` endpoint
- `apps/api/src/smallworld_api/models/previews.py` — `PreviewCapabilitiesResponse` model
- `apps/api/src/smallworld_api/config.py` — `preview_eager_count` setting

## Validation

- `pnpm test:api` passes all preview tests including new capabilities and delegation contract tests
- `pnpm lint:web` passes for all TypeScript changes
- Capabilities endpoint returns correct provider chains for all key permutations
- Error responses from the API include `detail` field (verified by contract tests)

## Follow-ups

- Remove the deprecated Playwright renderer once delegation is stable in production
- Add health check to capabilities endpoint to verify API reachability
- Consider caching capabilities response with short TTL
