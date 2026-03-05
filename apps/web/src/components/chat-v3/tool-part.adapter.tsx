"use client";

import { memo } from "react";
import {
  ToolCallMessagePartComponent,
  ToolCallMessagePartStatus,
} from "@assistant-ui/react";
import { Tool, ToolPart } from "@/components/ui/tool";

function mapStatus(
  status: ToolCallMessagePartStatus
): ToolPart["state"] {
  switch (status.type) {
    case "running":
      return "input-streaming";
    case "requires-action":
      return "input-available";
    case "complete":
      return "output-available";
    case "incomplete":
      return "output-error";
    default: {
      const _exhaustive: never = status;
      void _exhaustive;
      return "output-error";
    }
  }
}

function toOutputRecord(result: unknown): Record<string, unknown> | undefined {
  if (result === undefined || result === null) {
    return undefined;
  }
  if (typeof result === "string") {
    return { result };
  }
  if (typeof result === "object" && !Array.isArray(result)) {
    return result as Record<string, unknown>;
  }
  return { result: JSON.stringify(result) };
}

function extractErrorText(status: ToolCallMessagePartStatus): string | undefined {
  if (status.type !== "incomplete") {
    return undefined;
  }
  const { error } = status;
  if (error === undefined || error === null) {
    return undefined;
  }
  if (typeof error === "string") {
    return error;
  }
  return JSON.stringify(error);
}

const ToolPartAdapterInner: ToolCallMessagePartComponent = ({
  toolName,
  args,
  result,
  status,
  toolCallId,
}) => {
  const toolPart: ToolPart = {
    type: toolName,
    state: mapStatus(status),
    input: args as Record<string, unknown>,
    output: toOutputRecord(result),
    toolCallId,
    errorText: extractErrorText(status),
  };

  return <Tool toolPart={toolPart} />;
};

export const ToolPartAdapter = memo(ToolPartAdapterInner) as ToolCallMessagePartComponent;
