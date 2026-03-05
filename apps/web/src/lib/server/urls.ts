/** Centralized service URLs — single source of truth for fallback defaults. */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:4180";

export const MCP_SERVER_URL =
  process.env.MCP_SERVER_URL ?? "http://127.0.0.1:4181/mcp";

export const PREVIEW_RENDER_BASE_URL =
  process.env.PREVIEW_RENDER_BASE_URL || "http://localhost:4182";
