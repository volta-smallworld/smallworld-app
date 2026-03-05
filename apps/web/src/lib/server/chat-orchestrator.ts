import OpenAI from "openai";
import crypto from "crypto";
import { ToolRun, StreamEvent, RenderArtifact } from "@/types/chat";
import { listMcpTools, callMcpTool } from "@/lib/server/mcp-client";
import { MCP_SERVER_URL } from "@/lib/server/urls";
import { isToolLoggingEnabled, appendToolLog } from "@/lib/server/tool-log-store";
import { appendConversationLog } from "@/lib/server/conversation-log-store";
import { buildSystemPrompt } from "@/lib/server/chat-system-prompt";

const apiKey = process.env.DEEPSEEK_API_KEY;
const model = process.env.DEEPSEEK_MODEL ?? "deepseek-chat";
const maxToolRounds = parseInt(process.env.CHAT_MAX_TOOL_ROUNDS ?? "8", 10);
const maxToolOutputChars = parseInt(
  process.env.CHAT_MAX_TOOL_OUTPUT_CHARS ?? "50000",
  10
);

/**
 * Extract a RenderArtifact from a successful preview_render_pose tool call.
 * Uses output metadata for camera (reflects post-clamping) and input for
 * scene/composition/viewport/enhancement (not modified server-side).
 */
function extractRenderArtifact(
  toolName: string,
  input: Record<string, unknown>,
  output: string,
): RenderArtifact | null {
  if (toolName !== "preview_render_pose") return null;

  try {
    const result = JSON.parse(output);
    if (!result.id || !result.metadata?.camera) return null;

    const cam = result.metadata.camera;
    const loc = result.metadata.location;
    const scene = result.metadata.scene;
    const comp = result.metadata.composition;

    return {
      id: result.id,
      createdAt: new Date().toISOString(),
      summary: result.metadata.summary ?? "",
      camera: {
        position: {
          lat: cam.lat,
          lng: cam.lng,
          alt_meters: cam.alt_meters,
        },
        heading_deg: cam.heading_deg,
        pitch_deg: cam.pitch_deg,
        roll_deg: cam.roll_deg ?? 0,
        fov_deg: cam.fov_deg,
      },
      scene: {
        center: loc?.scene_center ?? {
          lat: (input.center_lat as number) ?? 0,
          lng: (input.center_lng as number) ?? 0,
        },
        radius_meters: loc?.radius_meters ?? (input.radius_meters as number) ?? 0,
        scene_id: scene?.scene_id ?? undefined,
        scene_type: scene?.scene_type ?? undefined,
      },
      composition: {
        target_template: comp?.target?.template ?? (input.target_template as string) ?? "",
        subject_label: comp?.target?.subject_label ?? (input.subject_label as string) ?? undefined,
        horizon_ratio: comp?.target?.horizon_ratio ?? (input.horizon_ratio as number) ?? undefined,
        anchors: (input.anchors as RenderArtifact["composition"]["anchors"]) ?? undefined,
      },
      viewport: input.viewport_width
        ? { width: input.viewport_width as number, height: (input.viewport_height as number) ?? 1024 }
        : undefined,
      enhancement: input.enhance !== undefined
        ? { enabled: !!input.enhance, prompt: (input.enhance_prompt as string) ?? undefined }
        : undefined,
    };
  } catch {
    return null;
  }
}

/** Convert MCP tools to OpenAI function-calling format */
function toOpenAITools(mcpTools: Array<{ name: string; description?: string; inputSchema: unknown }>): OpenAI.ChatCompletionTool[] {
  return mcpTools.map((tool) => ({
    type: "function" as const,
    function: {
      name: tool.name,
      description: tool.description ?? "",
      parameters: tool.inputSchema as Record<string, unknown>,
    },
  }));
}

export async function orchestrateChat(
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  requestId?: string,
  sessionId?: string,
  artifacts?: RenderArtifact[],
): Promise<{
  assistantText: string;
  toolRuns: ToolRun[];
  artifacts: RenderArtifact[];
  usage: { inputTokens: number; outputTokens: number };
}> {
  const orchestrationStartMs = Date.now();

  if (!apiKey) {
    throw new Error("DEEPSEEK_API_KEY is not configured");
  }

  const client = new OpenAI({
    apiKey,
    baseURL: "https://api.deepseek.com",
  });

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
        metadata: { mcpServerUrl: MCP_SERVER_URL },
      }).catch(() => {});
    } catch {}
  }

  const tools = toOpenAITools(mcpTools);

  const sessionArtifacts: RenderArtifact[] = [...(artifacts ?? [])];

  const openaiMessages: OpenAI.ChatCompletionMessageParam[] = [
    { role: "system", content: buildSystemPrompt(sessionArtifacts.length > 0 ? sessionArtifacts : undefined) },
    ...messages.map((m): OpenAI.ChatCompletionMessageParam => ({
      role: m.role,
      content: m.content,
    })),
  ];

  const toolRuns: ToolRun[] = [];
  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  let assistantText = "";

  for (let round = 0; round < maxToolRounds; round++) {
    const response = await client.chat.completions.create({
      model,
      max_tokens: 4096,
      messages: openaiMessages,
      tools: tools.length > 0 ? tools : undefined,
    });

    const choice = response.choices[0];
    const message = choice.message;

    totalInputTokens += response.usage?.prompt_tokens ?? 0;
    totalOutputTokens += response.usage?.completion_tokens ?? 0;

    const toolCalls = message.tool_calls ?? [];

    if (toolCalls.length === 0) {
      assistantText = message.content ?? "";
      break;
    }

    // Append assistant message (with tool_calls) to conversation
    openaiMessages.push(message);

    // Execute each tool call and collect results
    for (const toolCall of toolCalls) {
      if (toolCall.type !== "function") continue;
      const fnName = toolCall.function.name;
      let fnArgs: Record<string, unknown> = {};
      try {
        fnArgs = JSON.parse(toolCall.function.arguments);
      } catch {}

      const startedAt = new Date().toISOString();
      const startMs = Date.now();

      let toolOutput = "";
      let isError = false;
      let errorMessage: string | undefined;

      try {
        const result = await callMcpTool(fnName, fnArgs);
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

      // Extract render artifact from successful preview calls
      if (!isError) {
        const artifact = extractRenderArtifact(fnName, fnArgs, toolOutput);
        if (artifact) {
          sessionArtifacts.push(artifact);
        }
      }

      // Truncate output if needed
      const truncatedOutput =
        toolOutput.length > maxToolOutputChars
          ? toolOutput.slice(0, maxToolOutputChars) +
            `\n[output truncated at ${maxToolOutputChars} chars]`
          : toolOutput;

      const toolRun: ToolRun = {
        toolName: fnName,
        input: fnArgs,
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
          toolName: fnName,
          startedAt,
          endedAt: new Date().toISOString(),
          durationMs,
          isError,
          errorMessage,
          input: fnArgs,
          output: toolOutput,
          metadata: { mcpServerUrl: MCP_SERVER_URL, round },
        }).catch(() => {});
      }

      // Append tool result as a message
      openaiMessages.push({
        role: "tool",
        tool_call_id: toolCall.id,
        content: truncatedOutput,
      });
    }
  }

  if (sessionId && requestId) {
    const lastUserMsg = messages.filter((m) => m.role === "user").pop();
    appendConversationLog({
      id: crypto.randomUUID(),
      sessionId,
      requestId,
      timestamp: new Date().toISOString(),
      userMessage: lastUserMsg?.content ?? "",
      assistantResponse: assistantText,
      toolRuns: toolRuns.map((t) => ({
        toolName: t.toolName,
        durationMs: t.durationMs,
        isError: t.isError,
      })),
      usage: { inputTokens: totalInputTokens, outputTokens: totalOutputTokens },
      durationMs: Date.now() - orchestrationStartMs,
    }).catch(() => {});
  }

  return {
    assistantText,
    toolRuns,
    artifacts: sessionArtifacts,
    usage: {
      inputTokens: totalInputTokens,
      outputTokens: totalOutputTokens,
    },
  };
}

export async function orchestrateChatStream(
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  emit: (event: StreamEvent) => void,
  requestId?: string,
  sessionId?: string,
  artifacts?: RenderArtifact[],
): Promise<void> {
  const orchestrationStartMs = Date.now();

  if (!apiKey) {
    emit({ type: "error", message: "DEEPSEEK_API_KEY is not configured", code: "config_error" });
    return;
  }

  try {
    const client = new OpenAI({
      apiKey,
      baseURL: "https://api.deepseek.com",
    });

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
          metadata: { mcpServerUrl: MCP_SERVER_URL },
        }).catch(() => {});
      } catch {}
    }

    const tools = toOpenAITools(mcpTools);

    const sessionArtifacts: RenderArtifact[] = [...(artifacts ?? [])];

    const openaiMessages: OpenAI.ChatCompletionMessageParam[] = [
      { role: "system", content: buildSystemPrompt(sessionArtifacts.length > 0 ? sessionArtifacts : undefined) },
      ...messages.map((m): OpenAI.ChatCompletionMessageParam => ({
        role: m.role,
        content: m.content,
      })),
    ];

    const toolRuns: ToolRun[] = [];
    let totalInputTokens = 0;
    let totalOutputTokens = 0;
    let assistantText = "";

    for (let round = 0; round < maxToolRounds; round++) {
      if (round > 0) {
        emit({ type: "status", message: `Continuing analysis (round ${round + 1})...` });
      }

      // Stream the response
      const stream = await client.chat.completions.create({
        model,
        max_tokens: 4096,
        messages: openaiMessages,
        tools: tools.length > 0 ? tools : undefined,
        stream: true,
        stream_options: { include_usage: true },
      });

      let responseContent = "";
      const toolCalls: Map<number, { id: string; name: string; arguments: string }> = new Map();

      for await (const chunk of stream) {
        const delta = chunk.choices?.[0]?.delta;

        // Accumulate text content and emit deltas
        if (delta?.content) {
          responseContent += delta.content;
          emit({ type: "text_delta", delta: delta.content });
        }

        // Accumulate tool calls from deltas
        if (delta?.tool_calls) {
          for (const tc of delta.tool_calls) {
            const existing = toolCalls.get(tc.index);
            if (existing) {
              existing.arguments += tc.function?.arguments ?? "";
            } else {
              toolCalls.set(tc.index, {
                id: tc.id ?? "",
                name: tc.function?.name ?? "",
                arguments: tc.function?.arguments ?? "",
              });
            }
          }
        }

        // Capture usage from the final chunk
        if (chunk.usage) {
          totalInputTokens += chunk.usage.prompt_tokens ?? 0;
          totalOutputTokens += chunk.usage.completion_tokens ?? 0;
        }
      }

      if (toolCalls.size === 0) {
        assistantText = responseContent;
        break;
      }

      // Collect assistant text from this round
      if (responseContent) {
        assistantText += responseContent;
      }

      // Build the assistant message with tool_calls for the conversation
      const toolCallsArray: OpenAI.ChatCompletionMessageToolCall[] = Array.from(toolCalls.values()).map((tc) => ({
        id: tc.id,
        type: "function" as const,
        function: { name: tc.name, arguments: tc.arguments },
      }));

      openaiMessages.push({
        role: "assistant",
        content: responseContent || null,
        tool_calls: toolCallsArray,
      });

      // Execute each tool call
      for (const tc of toolCallsArray) {
        const fnName = tc.function.name;
        let fnArgs: Record<string, unknown> = {};
        try {
          fnArgs = JSON.parse(tc.function.arguments);
        } catch {}

        const startedAt = new Date().toISOString();
        const startMs = Date.now();

        emit({
          type: "tool_start",
          toolName: fnName,
          input: fnArgs,
          startedAt,
        });

        let toolOutput = "";
        let isError = false;
        let errorMessage: string | undefined;

        try {
          const result = await callMcpTool(fnName, fnArgs);
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

        // Extract render artifact from successful preview calls
        if (!isError) {
          const artifact = extractRenderArtifact(fnName, fnArgs, toolOutput);
          if (artifact) {
            sessionArtifacts.push(artifact);
          }
        }

        // Truncate output if needed
        const truncatedOutput =
          toolOutput.length > maxToolOutputChars
            ? toolOutput.slice(0, maxToolOutputChars) +
              `\n[output truncated at ${maxToolOutputChars} chars]`
            : toolOutput;

        const toolRun: ToolRun = {
          toolName: fnName,
          input: fnArgs,
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
            toolName: fnName,
            startedAt,
            endedAt: new Date().toISOString(),
            durationMs,
            isError,
            errorMessage,
            input: fnArgs,
            output: toolOutput,
            metadata: { mcpServerUrl: MCP_SERVER_URL, round },
          }).catch(() => {});
        }

        emit({
          type: "tool_end",
          toolName: fnName,
          output: truncatedOutput,
          isError,
          errorMessage,
          durationMs,
          startedAt,
        });

        // Append tool result
        openaiMessages.push({
          role: "tool",
          tool_call_id: tc.id,
          content: truncatedOutput,
        });
      }
    }

    if (sessionId && requestId) {
      const lastUserMsg = messages.filter((m) => m.role === "user").pop();
      appendConversationLog({
        id: crypto.randomUUID(),
        sessionId,
        requestId,
        timestamp: new Date().toISOString(),
        userMessage: lastUserMsg?.content ?? "",
        assistantResponse: assistantText,
        toolRuns: toolRuns.map((t) => ({
          toolName: t.toolName,
          durationMs: t.durationMs,
          isError: t.isError,
        })),
        usage: { inputTokens: totalInputTokens, outputTokens: totalOutputTokens },
        durationMs: Date.now() - orchestrationStartMs,
      }).catch(() => {});
    }

    emit({
      type: "done",
      id: crypto.randomUUID(),
      content: assistantText,
      toolRuns,
      artifacts: sessionArtifacts.length > 0 ? sessionArtifacts : undefined,
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
