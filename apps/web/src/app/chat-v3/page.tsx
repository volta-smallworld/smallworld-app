"use client";

import { Thread } from "@/components/chat-v3/thread";
import { useRuntimeSessionId } from "@/components/chat-v3/runtime-provider";
import { DevSessionBadge } from "@/components/dev-session-badge";

export default function ChatV3Page() {
  const sessionId = useRuntimeSessionId();

  return (
    <div className="flex h-screen w-full flex-col bg-[#18181B]">
      <header className="flex shrink-0 items-center justify-between border-b border-white/[0.08] px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tracking-wide text-white/90">
            SmallWorld
          </span>
          <DevSessionBadge sessionId={sessionId} />
        </div>
      </header>
      <main className="flex-1 overflow-hidden">
        <Thread />
      </main>
    </div>
  );
}
