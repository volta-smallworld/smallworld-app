"use client";

import {
  AuiIf,
  ComposerPrimitive,
} from "@assistant-ui/react";
import {
  PromptInput,
  PromptInputActions,
  PromptInputAction,
} from "@/components/ui/prompt-input";
import { Button } from "@/components/ui/button";
import { ArrowUpIcon, SquareIcon } from "lucide-react";

export function Composer() {
  return (
    <ComposerPrimitive.Root className="relative flex w-full flex-col">
      <PromptInput className="border-white/[0.08] bg-white/[0.03] has-[textarea:focus-visible]:border-[#7E3AF2]/60 has-[textarea:focus-visible]:ring-2 has-[textarea:focus-visible]:ring-[#7E3AF2]/20">
        <ComposerPrimitive.Input
          placeholder="Ask about terrain, viewpoints, or anything..."
          className="mb-1 max-h-32 min-h-14 w-full resize-none bg-transparent px-4 pt-2 pb-3 text-sm text-white/90 outline-none placeholder:text-white/30 focus-visible:ring-0 focus-visible:ring-offset-0"
          rows={1}
          autoFocus
          aria-label="Message input"
        />
        <PromptInputActions className="mx-2 mb-2 justify-end">
          <AuiIf condition={(s) => !s.thread.isRunning}>
            <PromptInputAction tooltip="Send message" side="bottom">
              <ComposerPrimitive.Send asChild>
                <Button
                  type="button"
                  variant="default"
                  size="icon"
                  className="size-8 rounded-full bg-[#7E3AF2] text-white hover:bg-[#6D2FD5]"
                  aria-label="Send message"
                >
                  <ArrowUpIcon className="size-4" />
                </Button>
              </ComposerPrimitive.Send>
            </PromptInputAction>
          </AuiIf>
          <AuiIf condition={(s) => s.thread.isRunning}>
            <PromptInputAction tooltip="Stop generating" side="bottom">
              <ComposerPrimitive.Cancel asChild>
                <Button
                  type="button"
                  variant="default"
                  size="icon"
                  className="size-8 rounded-full"
                  aria-label="Stop generating"
                >
                  <SquareIcon className="size-3 fill-current" />
                </Button>
              </ComposerPrimitive.Cancel>
            </PromptInputAction>
          </AuiIf>
        </PromptInputActions>
      </PromptInput>
    </ComposerPrimitive.Root>
  );
}
