"use client";

import { memo } from "react";
import { type ReasoningMessagePartComponent } from "@assistant-ui/react";
import {
  Reasoning,
  ReasoningTrigger,
  ReasoningContent,
} from "@/components/ui/reasoning";

const ReasoningPartAdapter: ReasoningMessagePartComponent = memo(
  function ReasoningPartAdapter({ text, status }) {
    const isStreaming = status.type === "running";

    return (
      <Reasoning isStreaming={isStreaming}>
        <ReasoningTrigger>Thinking...</ReasoningTrigger>
        <ReasoningContent markdown>{text}</ReasoningContent>
      </Reasoning>
    );
  }
);

export { ReasoningPartAdapter };
