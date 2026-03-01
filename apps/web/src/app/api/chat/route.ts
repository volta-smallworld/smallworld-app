import crypto from "crypto";
import { NextResponse } from "next/server";
import { orchestrateChat, orchestrateChatStream } from "@/lib/server/chat-orchestrator";
import type { ChatRequest, StreamEvent } from "@/types/chat";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  try {
    const body = await request.json() as ChatRequest;

    // Validate messages array
    if (!Array.isArray(body.messages) || body.messages.length === 0) {
      return NextResponse.json(
        { error: "Invalid request: messages array required" },
        { status: 400 }
      );
    }

    // Validate each message has role and content as strings
    for (const message of body.messages) {
      if (
        typeof message.role !== "string" ||
        typeof message.content !== "string"
      ) {
        return NextResponse.json(
          { error: "Invalid request: messages array required" },
          { status: 400 }
        );
      }
    }

    const requestId = crypto.randomUUID();

    // Streaming SSE path
    if (body.stream) {
      const stream = new ReadableStream({
        async start(controller) {
          const encoder = new TextEncoder();
          const send = (event: StreamEvent) => {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
          };
          try {
            await orchestrateChatStream(
              body.messages.map((m) => ({ role: m.role, content: m.content })),
              send,
              requestId
            );
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            send({ type: "error", message });
          } finally {
            controller.close();
          }
        },
      });
      return new Response(stream, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
      });
    }

    // Call orchestrateChat with normalized messages
    const result = await orchestrateChat(
      body.messages.map((m) => ({
        role: m.role,
        content: m.content,
      })),
      requestId
    );

    // Return success response
    return NextResponse.json({
      assistant: {
        id: crypto.randomUUID(),
        role: "assistant",
        content: result.assistantText,
      },
      toolRuns: result.toolRuns,
      usage: result.usage,
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);

    // Handle Anthropic API key error
    if (errorMessage.includes("ANTHROPIC_API_KEY")) {
      return NextResponse.json(
        {
          error: "Anthropic API key not configured",
          code: "config_error",
        },
        { status: 500 }
      );
    }

    // Handle MCP server unreachable error
    if (errorMessage.includes("MCP server unreachable")) {
      return NextResponse.json(
        {
          error: "MCP server is unavailable",
          code: "mcp_unavailable",
        },
        { status: 503 }
      );
    }

    // Generic error handling
    console.error("[chat] orchestration error:", errorMessage);
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}
