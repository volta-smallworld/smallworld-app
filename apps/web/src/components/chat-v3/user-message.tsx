"use client";

import { MessagePrimitive } from "@assistant-ui/react";
import { Message, MessageContent } from "@/components/ui/message";
import { cn } from "@/lib/utils";

export function UserMessage() {
  return (
    <MessagePrimitive.Root
      className={cn(
        "mx-auto grid w-full max-w-[44rem] auto-rows-auto",
        "grid-cols-[minmax(72px,1fr)_auto] gap-y-2 px-2 py-3",
        "animate-in fade-in slide-in-from-bottom-1 duration-150",
      )}
      data-role="user"
    >
      <div className="col-start-2 min-w-0">
        <Message>
          <MessageContent className="wrap-break-word rounded-2xl bg-white/[0.06] px-4 py-2.5 text-white/90">
            <MessagePrimitive.Parts />
          </MessageContent>
        </Message>
      </div>
    </MessagePrimitive.Root>
  );
}
