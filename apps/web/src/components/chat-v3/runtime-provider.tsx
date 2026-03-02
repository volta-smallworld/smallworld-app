"use client";

import { type ReactNode, createContext, useContext, useEffect } from "react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
  useAui,
  Suggestions,
} from "@assistant-ui/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { smallworldModelAdapter, setChatSessionId } from "@/lib/chat-model-adapter";
import { useSessionId } from "@/hooks/use-session-id";

const SessionIdContext = createContext<string>("");

export function useRuntimeSessionId() {
  return useContext(SessionIdContext);
}

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const { sessionId } = useSessionId();

  useEffect(() => {
    setChatSessionId(sessionId);
  }, [sessionId]);

  const runtime = useLocalRuntime(smallworldModelAdapter, {
    maxSteps: 8,
    initialMessages: [],
  });

  const aui = useAui({
    suggestions: Suggestions([
      {
        title: "Analyze terrain",
        label: "around Mount Rainier",
        prompt: "Analyze terrain around Mount Rainier",
      },
      {
        title: "Find viewpoints",
        label: "for Yosemite Valley",
        prompt: "Find viewpoints for Yosemite Valley",
      },
      {
        title: "Render a preview",
        label: "of the Grand Canyon at sunset",
        prompt: "Render a preview of the Grand Canyon at sunset",
      },
      {
        title: "Explore elevation",
        label: "around Lake Tahoe",
        prompt: "Explore elevation around Lake Tahoe",
      },
    ]),
  });

  return (
    <SessionIdContext.Provider value={sessionId}>
      <AssistantRuntimeProvider aui={aui} runtime={runtime}>
        <TooltipProvider>{children}</TooltipProvider>
      </AssistantRuntimeProvider>
    </SessionIdContext.Provider>
  );
}
