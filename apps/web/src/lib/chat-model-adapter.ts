import type { ChatModelAdapter, ChatModelRunResult } from "@assistant-ui/react";
import type { StreamEvent } from "@/types/chat";

/**
 * Module-level session ID for attaching to chat requests.
 * Set from the runtime-provider via `setChatSessionId()`.
 */
let _chatSessionId: string | undefined;

export function setChatSessionId(id: string) {
  _chatSessionId = id;
}

/**
 * Bridges the existing /api/chat SSE endpoint to assistant-ui's LocalRuntime.
 *
 * The adapter POSTs to /api/chat?stream=true, reads SSE events, and yields
 * content parts (text + tool-call) that the runtime understands.
 */
export const smallworldModelAdapter: ChatModelAdapter = {
  async *run({ messages, abortSignal }) {
    // Convert assistant-ui ThreadMessages to our API's expected format
    const apiMessages = messages.map((m) => ({
      id: m.id,
      role: m.role as "user" | "assistant",
      content: m.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("\n"),
    }));

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (_chatSessionId) {
      headers["X-Session-Id"] = _chatSessionId;
    }

    const res = await fetch("/api/chat", {
      method: "POST",
      headers,
      body: JSON.stringify({ messages: apiMessages, stream: true }),
      signal: abortSignal,
    });

    if (!res.ok || !res.body) {
      let errorMsg = res.statusText;
      try {
        const errBody = await res.json();
        errorMsg = errBody.error ?? errorMsg;
      } catch {
        // use statusText
      }
      throw new Error(errorMsg);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // Ordered parts array — preserves chronological interleaving of text and tool calls
    const parts: ContentPart[] = [];
    const pendingToolCallIndexes = new Map<string, number[]>();
    let toolCallCounter = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const json = line.slice(6);
        if (!json) continue;

        let event: StreamEvent;
        try {
          event = JSON.parse(json) as StreamEvent;
        } catch {
          continue;
        }

        switch (event.type) {
          case "text_delta": {
            // Append to the last text part, or start a new one
            const last = parts[parts.length - 1];
            if (last && last.type === "text") {
              last.text += event.delta;
            } else {
              parts.push({ type: "text", text: event.delta });
            }
            break;
          }

          case "tool_start": {
            const callId = `call_${toolCallCounter++}`;
            const index = parts.push({
              type: "tool-call",
              toolCallId: callId,
              toolName: event.toolName,
              args: event.input,
            }) - 1;

            const queue = pendingToolCallIndexes.get(event.toolName);
            if (queue) {
              queue.push(index);
            } else {
              pendingToolCallIndexes.set(event.toolName, [index]);
            }
            break;
          }

          case "tool_end": {
            const queue = pendingToolCallIndexes.get(event.toolName);
            const index = queue?.shift();

            if (queue && queue.length === 0) {
              pendingToolCallIndexes.delete(event.toolName);
            }

            if (index !== undefined) {
              const part = parts[index];
              if (part.type === "tool-call") {
                part.result = event.output;
                part.isError = event.isError;
              }
            } else {
              // Preserve the result even if a start event was missed.
              const callId = `call_${toolCallCounter++}`;
              parts.push({
                type: "tool-call",
                toolCallId: callId,
                toolName: event.toolName,
                args: {},
                result: event.output,
                isError: event.isError,
              });
            }
            break;
          }

          case "done":
            // Don't overwrite parts — the streamed order is authoritative.
            // The done.content field is a flat concatenation that would
            // destroy interleaving.
            break;

          case "error":
            throw new Error(event.message);

          case "status":
            // Status updates (e.g., "Continuing analysis...") — no-op
            break;
        }

        // Yield accumulated state after every event
        yield buildResult(parts);
      }
    }

    // Final yield
    yield buildResult(parts);
  },
};

function buildResult(parts: ContentPart[]): ChatModelRunResult {
  const content: ChatModelRunResult["content"] = [];

  for (const part of parts) {
    if (part.type === "text") {
      (content as unknown[]).push({ type: "text" as const, text: part.text });
    } else {
      (content as unknown[]).push({
        type: "tool-call" as const,
        toolCallId: part.toolCallId,
        toolName: part.toolName,
        args: part.args,
        argsText: JSON.stringify(part.args, null, 2),
        result: part.result,
        isError: part.isError,
      });
    }
  }

  return { content };
}

type ContentPart =
  | { type: "text"; text: string }
  | {
      type: "tool-call";
      toolCallId: string;
      toolName: string;
      args: Record<string, unknown>;
      result?: string;
      isError?: boolean;
    };
