"use client";

import {
  ActionBarPrimitive,
  AuiIf,
  MessagePrimitive,
} from "@assistant-ui/react";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { Message, MessageContent, MessageActions } from "@/components/ui/message";
import { ToolPartAdapter } from "@/components/chat-v3/tool-part.adapter";
import { CheckIcon, CopyIcon, RefreshCwIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function AssistantMessage() {
  return (
    <MessagePrimitive.Root
      className={cn(
        "mx-auto w-full max-w-[44rem]",
        "animate-in fade-in slide-in-from-bottom-1 py-3 duration-150",
      )}
      data-role="assistant"
    >
      <Message className="flex-col gap-1">
        <MessageContent className="bg-transparent p-0 rounded-none text-white/90 wrap-break-word leading-relaxed">
          <MessagePrimitive.Parts
            components={{
              Text: MarkdownText,
              tools: {
                Fallback: ToolPartAdapter,
              },
            }}
          />
        </MessageContent>

        <ActionBarPrimitive.Root
          hideWhenRunning
          autohide="not-last"
          className="mt-1 ml-2"
        >
          <MessageActions className="-ml-1 text-white/40">
            <ActionBarPrimitive.Copy asChild>
              <TooltipIconButton tooltip="Copy">
                <AuiIf condition={(s) => s.message.isCopied}>
                  <CheckIcon />
                </AuiIf>
                <AuiIf condition={(s) => !s.message.isCopied}>
                  <CopyIcon />
                </AuiIf>
              </TooltipIconButton>
            </ActionBarPrimitive.Copy>
            <ActionBarPrimitive.Reload asChild>
              <TooltipIconButton tooltip="Retry">
                <RefreshCwIcon />
              </TooltipIconButton>
            </ActionBarPrimitive.Reload>
          </MessageActions>
        </ActionBarPrimitive.Root>
      </Message>
    </MessagePrimitive.Root>
  );
}
