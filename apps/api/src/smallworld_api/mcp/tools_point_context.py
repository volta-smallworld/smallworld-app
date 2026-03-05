"""MCP tool: terrain_point_context."""

from __future__ import annotations

import httpx

from smallworld_api.mcp.schemas import TerrainPointContextInput
from smallworld_api.mcp.server import mcp
from smallworld_api.services.point_context import get_point_context


@mcp.tool()
async def terrain_point_context(
    lat: float,
    lng: float,
    camera_altitude_meters: float | None = None,
    context_radius_meters: float = 2000,
    zoom: int | None = None,
) -> dict:
    """Get precise ground elevation and local terrain context for a point.

    Returns raw-tile-resolution elevation (not the coarse 128x128 grid),
    optional camera AGL (Above Ground Level), and local terrain derivatives
    (slope, curvature, relief) within a configurable context radius.

    Use this to check whether a camera position is underground or to
    understand the terrain characteristics at a specific location.

    Args:
        lat: Latitude (-90 to 90)
        lng: Longitude (-180 to 180)
        camera_altitude_meters: Optional camera altitude to compute AGL clearance
        context_radius_meters: Radius for local terrain analysis (500 to 10000, default 2000)
        zoom: Tile zoom level override (default: 14)
    """
    # Validate input via Pydantic
    inp = TerrainPointContextInput(
        lat=lat, lng=lng,
        camera_altitude_meters=camera_altitude_meters,
        context_radius_meters=context_radius_meters,
        zoom=zoom,
    )

    try:
        result = await get_point_context(
            lat=inp.lat,
            lng=inp.lng,
            camera_altitude_meters=inp.camera_altitude_meters,
            context_radius_meters=inp.context_radius_meters,
            zoom=inp.zoom,
        )
    except ValueError as e:
        raise ValueError(f"Invalid point context request: {e}")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"Upstream tile fetch failed (HTTP {e.response.status_code}). Try again."
        )
    except httpx.RequestError as e:
        raise RuntimeError(f"Upstream tile fetch failed: {e}. Try again.")

    response: dict = {
        "ground_elevation_meters": result.ground_elevation_meters,
        "camera_agl_meters": result.camera_agl_meters,
        "sampling": result.sampling,
        "context": result.context,
    }
    return response
