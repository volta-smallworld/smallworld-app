import Anthropic from "@anthropic-ai/sdk";
import crypto from "crypto";
import { ToolRun, StreamEvent } from "@/types/chat";
import { listMcpTools, callMcpTool } from "@/lib/server/mcp-client";
import { isToolLoggingEnabled, appendToolLog } from "@/lib/server/tool-log-store";
import { CHAT_SYSTEM_PROMPT } from "@/lib/server/chat-system-prompt";

const apiKey = process.env.ANTHROPIC_API_KEY;
const model = process.env.ANTHROPIC_MODEL ?? "claude-sonnet-4-20250514";
const maxToolRounds = parseInt(process.env.CHAT_MAX_TOOL_ROUNDS ?? "8", 10);
const maxToolOutputChars = parseInt(
  process.env.CHAT_MAX_TOOL_OUTPUT_CHARS ?? "50000",
  10
);

export async function orchestrateChat(
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  requestId?: string
): Promise<{
  assistantText: string;
  toolRuns: ToolRun[];
  usage: { inputTokens: number; outputTokens: number };
}> {
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY is not configured");
  }

  const anthropic = new Anthropic({ apiKey });

  const discoveryStart = new Date().toISOString();
  const discoveryStartMs = Date.now();
  const mcpTools = await listMcpTools();

  if (requestId && isToolLoggingEnabled()) {
    try {
      const discoveryEnd = new Date().toISOString();
      appendToolLog({
        id: crypto.randomUUID(),
        eventType: "tool_discovery",
        requestId,
        toolName: "tools/list",
        startedAt: discoveryStart,
        endedAt: discoveryEnd,
        durationMs: Date.now() - discoveryStartMs,
        isError: false,
        input: {},
        output: JSON.stringify(mcpTools.map(t => t.name)),
        metadata: { mcpServerUrl: process.env.MCP_SERVER_URL ?? "http://127.0.0.1:8001/mcp" },
      }).catch(() => {});
    } catch {}
  }

  const tools: Anthropic.Tool[] = mcpTools.map((tool) => ({
    name: tool.name,
    description: tool.description ?? "",
    input_schema: tool.inputSchema as Anthropic.Tool["input_schema"],
  }));

  const anthropicMessages: Anthropic.MessageParam[] = messages.map((m) => ({
    role: m.role,
    content: m.content,
  }));

  const toolRuns: ToolRun[] = [];
  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  let assistantText = "";

  for (let round = 0; round < maxToolRounds; round++) {
    const response = await anthropic.messages.create({
      model,
      max_tokens: 4096,
      system: CHAT_SYSTEM_PROMPT,
      messages: anthropicMessages,
      tools,
    });

    totalInputTokens += response.usage.input_tokens;
    totalOutputTokens += response.usage.output_tokens;

    const toolUseBlocks = response.content.filter(
      (block): block is Anthropic.ToolUseBlock => block.type === "tool_use"
    );

    if (toolUseBlocks.length === 0) {
      // No tool calls — extract final text and return
      const textBlock = response.content.find(
        (block): block is Anthropic.TextBlock => block.type === "text"
      );
      assistantText = textBlock?.text ?? "";
      break;
    }

    // Append assistant response to messages
    anthropicMessages.push({ role: "assistant", content: response.content });

    // Execute each tool call and collect results
    const toolResultContent: Array<{
      type: "tool_result";
      tool_use_id: string;
      content: string;
      is_error?: boolean;
    }> = [];

    for (const block of toolUseBlocks) {
      const startedAt = new Date().toISOString();
      const startMs = Date.now();

      let toolOutput = "";
      let isError = false;
      let errorMessage: string | undefined;

      try {
        const result = await callMcpTool(
          block.name,
          block.input as Record<string, unknown>
        );
        toolOutput = result.content;
        isError = result.isError;
        if (result.isError) {
          errorMessage = result.content;
        }
      } catch (err) {
        isError = true;
        errorMessage = err instanceof Error ? err.message : String(err);
        toolOutput = errorMessage;
      }

      const durationMs = Date.now() - startMs;

      // Truncate output if needed
      const truncatedOutput =
        toolOutput.length > maxToolOutputChars
          ? toolOutput.slice(0, maxToolOutputChars) +
            `\n[output truncated at ${maxToolOutputChars} chars]`
          : toolOutput;

      const toolRun: ToolRun = {
        toolName: block.name,
        input: block.input as Record<string, unknown>,
        output: truncatedOutput,
        isError,
        errorMessage,
        durationMs,
        startedAt,
      };
      toolRuns.push(toolRun);

      if (requestId && isToolLoggingEnabled()) {
        appendToolLog({
          id: crypto.randomUUID(),
          eventType: "tool_call",
          requestId,
          toolName: block.name,
          startedAt,
          endedAt: new Date().toISOString(),
          durationMs,
          isError,
          errorMessage,
          input: block.input as Record<string, unknown>,
          output: toolOutput,
          metadata: { mcpServerUrl: process.env.MCP_SERVER_URL ?? "http://127.0.0.1:8001/mcp", round },
        }).catch(() => {});
      }

      toolResultContent.push({
        type: "tool_result" as const,
        tool_use_id: block.id,
        content: truncatedOutput,
        is_error: isError,
      });
    }

    // Append tool results as a user message
    anthropicMessages.push({ role: "user", content: toolResultContent });
  }

  return {
    assistantText,
    toolRuns,
    usage: {
      inputTokens: totalInputTokens,
      outputTokens: totalOutputTokens,
    },
  };
}

export async function orchestrateChatStream(
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  emit: (event: StreamEvent) => void,
  requestId?: string
): Promise<void> {
  if (!apiKey) {
    emit({ type: "error", message: "ANTHROPIC_API_KEY is not configured", code: "config_error" });
    return;
  }

  try {
    const anthropic = new Anthropic({ apiKey });

    const discoveryStart = new Date().toISOString();
    const discoveryStartMs = Date.now();
    const mcpTools = await listMcpTools();

    if (requestId && isToolLoggingEnabled()) {
      try {
        const discoveryEnd = new Date().toISOString();
        appendToolLog({
          id: crypto.randomUUID(),
          eventType: "tool_discovery",
          requestId,
          toolName: "tools/list",
          startedAt: discoveryStart,
          endedAt: discoveryEnd,
          durationMs: Date.now() - discoveryStartMs,
          isError: false,
          input: {},
          output: JSON.stringify(mcpTools.map(t => t.name)),
          metadata: { mcpServerUrl: process.env.MCP_SERVER_URL ?? "http://127.0.0.1:8001/mcp" },
        }).catch(() => {});
      } catch {}
    }

    const tools: Anthropic.Tool[] = mcpTools.map((tool) => ({
      name: tool.name,
      description: tool.description ?? "",
      input_schema: tool.inputSchema as Anthropic.Tool["input_schema"],
    }));

    const anthropicMessages: Anthropic.MessageParam[] = messages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    const toolRuns: ToolRun[] = [];
    let totalInputTokens = 0;
    let totalOutputTokens = 0;
    let assistantText = "";

    for (let round = 0; round < maxToolRounds; round++) {
      if (round > 0) {
        emit({ type: "status", message: `Continuing analysis (round ${round + 1})...` });
      }

      const stream = anthropic.messages.stream({
        model,
        max_tokens: 4096,
        system: CHAT_SYSTEM_PROMPT,
        messages: anthropicMessages,
        tools,
      });

      stream.on("text", (delta) => {
        emit({ type: "text_delta", delta });
      });

      const response = await stream.finalMessage();

      totalInputTokens += response.usage.input_tokens;
      totalOutputTokens += response.usage.output_tokens;

      const toolUseBlocks = response.content.filter(
        (block): block is Anthropic.ToolUseBlock => block.type === "tool_use"
      );

      if (toolUseBlocks.length === 0) {
        // No tool calls — extract final text
        const textBlock = response.content.find(
          (block): block is Anthropic.TextBlock => block.type === "text"
        );
        assistantText = textBlock?.text ?? "";
        break;
      }

      // Collect assistant text from this round
      const textBlock = response.content.find(
        (block): block is Anthropic.TextBlock => block.type === "text"
      );
      if (textBlock) {
        assistantText += textBlock.text;
      }

      // Append assistant response to messages
      anthropicMessages.push({ role: "assistant", content: response.content });

      // Execute each tool call
      const toolResultContent: Array<{
        type: "tool_result";
        tool_use_id: string;
        content: string;
        is_error?: boolean;
      }> = [];

      for (const block of toolUseBlocks) {
        const startedAt = new Date().toISOString();
        const startMs = Date.now();

        emit({
          type: "tool_start",
          toolName: block.name,
          input: block.input as Record<string, unknown>,
          startedAt,
        });

        let toolOutput = "";
        let isError = false;
        let errorMessage: string | undefined;

        try {
          const result = await callMcpTool(
            block.name,
            block.input as Record<string, unknown>
          );
          toolOutput = result.content;
          isError = result.isError;
          if (result.isError) {
            errorMessage = result.content;
          }
        } catch (err) {
          isError = true;
          errorMessage = err instanceof Error ? err.message : String(err);
          toolOutput = errorMessage;
        }

        const durationMs = Date.now() - startMs;

        // Truncate output if needed
        const truncatedOutput =
          toolOutput.length > maxToolOutputChars
            ? toolOutput.slice(0, maxToolOutputChars) +
              `\n[output truncated at ${maxToolOutputChars} chars]`
            : toolOutput;

        const toolRun: ToolRun = {
          toolName: block.name,
          input: block.input as Record<string, unknown>,
          output: truncatedOutput,
          isError,
          errorMessage,
          durationMs,
          startedAt,
        };
        toolRuns.push(toolRun);

        if (requestId && isToolLoggingEnabled()) {
          appendToolLog({
            id: crypto.randomUUID(),
            eventType: "tool_call",
            requestId,
            toolName: block.name,
            startedAt,
            endedAt: new Date().toISOString(),
            durationMs,
            isError,
            errorMessage,
            input: block.input as Record<string, unknown>,
            output: toolOutput,
            metadata: { mcpServerUrl: process.env.MCP_SERVER_URL ?? "http://127.0.0.1:8001/mcp", round },
          }).catch(() => {});
        }

        emit({
          type: "tool_end",
          toolName: block.name,
          output: truncatedOutput,
          isError,
          errorMessage,
          durationMs,
          startedAt,
        });

        toolResultContent.push({
          type: "tool_result" as const,
          tool_use_id: block.id,
          content: truncatedOutput,
          is_error: isError,
        });
      }

      // Append tool results as a user message
      anthropicMessages.push({ role: "user", content: toolResultContent });
    }

    emit({
      type: "done",
      id: crypto.randomUUID(),
      content: assistantText,
      toolRuns,
      usage: {
        inputTokens: totalInputTokens,
        outputTokens: totalOutputTokens,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    emit({ type: "error", message });
  }
}
