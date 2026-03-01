/**
 * Lightweight MCP client using direct JSON-RPC over HTTP.
 * Avoids the @modelcontextprotocol/sdk zod compatibility issues
 * by speaking the Streamable HTTP protocol directly.
 */

const MCP_SERVER_URL =
  process.env.MCP_SERVER_URL ?? "http://127.0.0.1:8001/mcp";

export interface McpTool {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

let sessionId: string | null = null;
let requestId = 0;

function nextId(): number {
  return ++requestId;
}

async function rpc(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json, text/event-stream",
  };
  if (sessionId) {
    headers["Mcp-Session-Id"] = sessionId;
  }

  const res = await fetch(MCP_SERVER_URL, {
    method: "POST",
    headers,
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: nextId(),
      method,
      params,
    }),
  });

  if (!res.ok) {
    throw new Error(`MCP server returned ${res.status}: ${res.statusText}`);
  }

  // Capture session ID from response headers
  const sid = res.headers.get("Mcp-Session-Id");
  if (sid) {
    sessionId = sid;
  }

  const contentType = res.headers.get("Content-Type") ?? "";

  // Handle SSE responses
  if (contentType.includes("text/event-stream")) {
    const text = await res.text();
    const lines = text.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        if (data.error) {
          throw new Error(data.error.message ?? JSON.stringify(data.error));
        }
        return data.result;
      }
    }
    throw new Error("No data event in SSE response");
  }

  // Handle JSON responses
  const data = await res.json();
  if (data.error) {
    throw new Error(data.error.message ?? JSON.stringify(data.error));
  }
  return data.result;
}

async function ensureInitialized(): Promise<void> {
  if (sessionId) return;

  try {
    await rpc("initialize", {
      protocolVersion: "2025-03-26",
      capabilities: {},
      clientInfo: { name: "smallworld-web", version: "1.0.0" },
    });

    // Send initialized notification (no id, no response expected)
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
    };
    if (sessionId) {
      headers["Mcp-Session-Id"] = sessionId;
    }
    await fetch(MCP_SERVER_URL, {
      method: "POST",
      headers,
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "notifications/initialized",
      }),
    });
  } catch {
    throw new Error(`MCP server unreachable at ${MCP_SERVER_URL}`);
  }
}

export async function listMcpTools(): Promise<McpTool[]> {
  await ensureInitialized();
  const result = (await rpc("tools/list")) as { tools: McpTool[] };
  return result.tools;
}

export async function callMcpTool(
  name: string,
  args: Record<string, unknown>
): Promise<{ content: string; isError: boolean }> {
  await ensureInitialized();
  const result = (await rpc("tools/call", { name, arguments: args })) as {
    content: Array<{ type: string; text?: string }>;
    isError?: boolean;
  };

  const content = (result.content ?? [])
    .filter((part) => part.type === "text" && part.text)
    .map((part) => part.text!)
    .join("");

  return { content, isError: result.isError === true };
}

export async function closeMcpClient(): Promise<void> {
  sessionId = null;
  requestId = 0;
}
