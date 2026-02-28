"""CLI entrypoint for the Smallworld MCP server.

Supports stdio and HTTP transports:
    uv run python -m smallworld_api.mcp.cli              # stdio (default)
    uv run python -m smallworld_api.mcp.cli --transport http  # Streamable HTTP
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Smallworld MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HTTP_HOST", "127.0.0.1"),
        help="HTTP host (default: 127.0.0.1 or MCP_HTTP_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_HTTP_PORT", "8001")),
        help="HTTP port (default: 8001 or MCP_HTTP_PORT)",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("MCP_HTTP_PATH", "/mcp"),
        help="HTTP path (default: /mcp or MCP_HTTP_PATH)",
    )
    args = parser.parse_args()

    from smallworld_api.mcp.server import mcp

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            path=args.path,
        )


if __name__ == "__main__":
    main()
