import { NextResponse } from "next/server";
import { isToolLoggingEnabled, listToolLogs, clearToolLogs } from "@/lib/server/tool-log-store";
import type { ToolLogEntry, ToolLogsResponse } from "@/types/chat";

export const runtime = "nodejs";

const uiMaxChars = parseInt(process.env.TOOL_LOG_UI_MAX_CHARS ?? "4000", 10);

function truncatePreview(value: unknown, maxChars: number): { preview: string; truncated: boolean } {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "";
  if (text.length <= maxChars) {
    return { preview: text, truncated: false };
  }
  return { preview: text.slice(0, maxChars) + "\n[truncated]", truncated: true };
}

export async function GET(request: Request): Promise<Response> {
  if (!isToolLoggingEnabled()) {
    return NextResponse.json({ error: "Tool logging is disabled" }, { status: 404 });
  }

  const url = new URL(request.url);
  const limit = parseInt(url.searchParams.get("limit") ?? "50", 10);
  const isErrorParam = url.searchParams.get("isError");
  const toolName = url.searchParams.get("toolName") ?? undefined;

  const isError = isErrorParam === "true" ? true : isErrorParam === "false" ? false : undefined;

  const records = await listToolLogs({ limit, isError, toolName });

  const entries: ToolLogEntry[] = records.map((r) => {
    const inp = truncatePreview(r.input, uiMaxChars);
    const out = truncatePreview(r.output, uiMaxChars);
    return {
      id: r.id,
      eventType: r.eventType,
      requestId: r.requestId,
      toolName: r.toolName,
      startedAt: r.startedAt,
      endedAt: r.endedAt,
      durationMs: r.durationMs,
      isError: r.isError,
      errorMessage: r.errorMessage,
      inputPreview: inp.preview,
      inputTruncated: inp.truncated,
      outputPreview: out.preview,
      outputTruncated: out.truncated,
      metadata: r.metadata,
    };
  });

  const response: ToolLogsResponse = { entries, total: entries.length };
  return NextResponse.json(response);
}

export async function DELETE(): Promise<Response> {
  if (!isToolLoggingEnabled()) {
    return NextResponse.json({ error: "Tool logging is disabled" }, { status: 404 });
  }

  await clearToolLogs();
  return NextResponse.json({ ok: true });
}
