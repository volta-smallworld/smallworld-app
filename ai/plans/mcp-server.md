# Smallworld MCP Server v1

## Summary
- Build an MCP server for Smallworld inside the existing Python backend stack, not as a new tech stack.
- Use the official Python FastMCP SDK, with one shared codebase that supports `stdio` for local clients and Streamable HTTP for remote/internal clients.
- Keep the current REST API unchanged and reuse the existing terrain service directly rather than proxying MCP calls through HTTP.
- Expose a narrow v1 surface: one primary terrain tool and two lightweight read-only resources.
- Optimize the MCP contract for agents: compact response by default, raw `128x128` elevation matrix only when explicitly requested.

## Public APIs and Interfaces
- Add a new MCP package under `apps/api/src/smallworld_api/mcp`.
- Add `mcp[cli]` to `apps/api` dependencies, pinned to `>=1,<2`.
  Inference from the official Python SDK README: `main` is v2 pre-alpha as of February 28, 2026, while v1.x is still the production-safe line.
- Keep existing REST endpoints unchanged:
  - `GET /healthz`
  - `POST /api/v1/terrain/elevation-grid`
- Add one MCP tool with an MCP-specific schema instead of mirroring the REST request verbatim.

```json
{
  "tool": "terrain_analyze_area",
  "description": "Fetch terrain elevation data and summary statistics for a circular area.",
  "input_schema": {
    "lat": "float, -90..90",
    "lng": "float, -180..180",
    "radius_meters": "float, 1000..50000",
    "zoom": "int | null, default null meaning server default",
    "include_elevations": "bool, default false"
  },
  "output_schema": {
    "request": {
      "lat": "float",
      "lng": "float",
      "radius_meters": "float",
      "zoom_used": "int"
    },
    "bounds": {
      "north": "float",
      "south": "float",
      "east": "float",
      "west": "float"
    },
    "grid": {
      "width": "int",
      "height": "int",
      "cell_size_meters_approx": "float",
      "elevations_included": "bool",
      "elevations": "float[][] | null"
    },
    "tile_count": "int",
    "tiles": [{"z": "int", "x": "int", "y": "int"}],
    "stats": {
      "min_elevation": "float",
      "max_elevation": "float",
      "mean_elevation": "float"
    },
    "source": "string"
  }
}
```

- Add two MCP resources:
  - `smallworld://server-info`
  - `smallworld://usage-guidance`
- Do not add prompts in v1.

## Implementation Plan
1. Create a dedicated MCP module tree with `server.py`, `tools.py`, `resources.py`, `schemas.py`, `adapters.py`, and `cli.py`.
2. Define MCP-specific Pydantic models in `schemas.py`.
   The MCP contract will use snake_case and flat `lat`/`lng` inputs because that is more LLM-friendly than the current nested REST request shape.
3. Add an adapter layer that converts the existing `get_elevation_grid()` result into the MCP result shape.
   The adapter will:
   - preserve current numerical values
   - add `tile_count`
   - rename keys to snake_case
   - omit `grid.elevations` unless `include_elevations=true`
4. Implement `terrain_analyze_area` in `tools.py`.
   The tool will call `smallworld_api.services.terrarium.get_elevation_grid()` directly.
   It will not call the REST route.
5. Implement the resources in `resources.py`.
   `smallworld://server-info` will expose version, source, grid size, default zoom, max tiles, and enabled transports.
   `smallworld://usage-guidance` will return compact Markdown explaining input bounds, expected cost, when to request full elevations, and common failure modes.
6. Build a FastMCP server in `server.py` with:
   - name `smallworld`
   - short instructions describing terrain-analysis behavior
   - `json_response=True`
   - `stateless_http=True` for HTTP mode
7. Build `cli.py` so the same server can run in two modes:
   - `stdio` for local IDE/desktop clients
   - `streamable-http` for remote/internal use
8. Default HTTP settings:
   - host `127.0.0.1`
   - port `8001`
   - path `/mcp`
   Add env overrides:
   - `MCP_HTTP_HOST`
   - `MCP_HTTP_PORT`
   - `MCP_HTTP_PATH`
9. Add root-level scripts for developer ergonomics:
   - `dev:mcp`
   - `dev:mcp:http`
   - `test:mcp` if the test suite is split out
10. Update repo docs:
   - README setup and run instructions
   - an ADR documenting why Smallworld uses explicit FastMCP tools, dual transport, and a separate entrypoint instead of mounting into the existing FastAPI app
11. Keep the MCP server as a separate process in v1.
   Inference from the official SDK docs and current repo shape: FastMCP can be mounted into an ASGI app, but a separate entrypoint is lower-risk here because `stdio` already requires its own runtime and the existing backend is intentionally simple.

## Error Handling and Operational Behavior
- Input validation failures must fail before the terrain service is called.
- Service `ValueError` from tile-cap overflow will surface as a clear tool error telling the caller to reduce radius.
- Upstream tile fetch failures will surface as retryable tool errors with a short, stable message.
- The tool must describe that it may fetch up to `MAX_TILES_PER_REQUEST` terrain tiles.
- The server must remain read-only. No mutating tools will be added.

## Test Cases and Scenarios
- Tool registration test: the server lists exactly one tool and two resources.
- Happy-path tool call with `include_elevations=false` returns stats, bounds, tiles, and `elevations=null`.
- Happy-path tool call with `include_elevations=true` returns a `128x128` matrix.
- Validation rejects out-of-range latitude, longitude, and radius.
- Oversized tile request returns a clear, stable error message.
- Upstream fetch failure returns a tool error rather than crashing the server.
- Resource read test for `smallworld://server-info`.
- Resource read test for `smallworld://usage-guidance`.
- Stdio smoke test: initialize a client session, list tools, call `terrain_analyze_area`.
- Streamable HTTP smoke test: start the server on `/mcp`, initialize a client session, list tools, call `terrain_analyze_area`.
- Backward-compatibility test: existing FastAPI route tests continue to pass unchanged.

## Acceptance Criteria
- A local MCP client can connect over `stdio`, discover `terrain_analyze_area`, and successfully call it.
- A remote/internal MCP client can connect to `http://localhost:8001/mcp` and perform the same flow.
- The MCP tool reuses the existing terrain pipeline and returns numerically consistent results with the REST implementation.
- The default MCP response is materially smaller than the REST payload because elevations are excluded unless requested.
- No existing web app behavior or REST contract changes.

## Assumptions and Defaults
- Scope is limited to read/compute terrain analysis for v1.
- The existing REST API remains the system of record for the browser app.
- The MCP server will be implemented in Python because the terrain logic already lives there.
- Remote HTTP support in v1 is for trusted/internal use, not public internet exposure.
- Protocol-level OAuth or other public-facing auth is deferred to a later phase if remote exposure becomes a real product requirement.
- SSE is excluded; Streamable HTTP is the only HTTP transport.
- Prompts are intentionally deferred.
- Auto-generated “wrap every FastAPI endpoint as a tool” approaches are out of scope; the MCP surface will be explicit and hand-designed.

## References
- [Build an MCP server](https://modelcontextprotocol.io/docs/develop/build-server)
- [Official MCP SDK overview](https://modelcontextprotocol.io/docs/sdk)
- [MCP server concepts](https://modelcontextprotocol.io/docs/learn/server-concepts)
- [MCP tools specification](https://modelcontextprotocol.io/specification/draft/server/tools)
- [MCP resources specification](https://modelcontextprotocol.io/specification/draft/server/resources)
- [MCP base protocol overview](https://modelcontextprotocol.io/specification/2025-06-18/basic)
- [Official Python SDK README](https://github.com/modelcontextprotocol/python-sdk)
