"""MCP server setup with FastMCP.

Creates the FastMCP server instance and registers tools and resources.
Supports stdio and Streamable HTTP transports.
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP(
    name="Smallworld MCP Server",
    instructions=(
        "Smallworld provides terrain analysis, viewpoint discovery, and "
        "preview rendering for landscape photography planning. "
        "Use terrain_analyze_area to understand terrain, "
        "terrain_find_viewpoints to discover camera poses, "
        "preview_render_pose to render a preview image, and "
        "terrain_point_context for precise ground elevation and camera safety checks."
    ),
)

# Import tools and resources to register them with the server
import smallworld_api.mcp.tools_terrain  # noqa: F401, E402
import smallworld_api.mcp.tools_viewpoints  # noqa: F401, E402
import smallworld_api.mcp.tools_previews  # noqa: F401, E402
import smallworld_api.mcp.tools_point_context  # noqa: F401, E402
import smallworld_api.mcp.resources  # noqa: F401, E402
