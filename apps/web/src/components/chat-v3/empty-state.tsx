"use client";

import {
  SuggestionPrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import { PromptSuggestion } from "@/components/ui/prompt-suggestion";
import type { FC } from "react";

export function EmptyState() {
  return (
    <div className="mx-auto my-auto flex w-full max-w-[44rem] grow flex-col">
      <div className="flex w-full grow flex-col items-center justify-center">
        <div className="flex size-full flex-col justify-center px-4">
          <h1 className="animate-in fade-in slide-in-from-bottom-1 fill-mode-both text-2xl font-semibold text-white duration-200">
            What can I help with?
          </h1>
          <p className="animate-in fade-in slide-in-from-bottom-1 fill-mode-both text-xl text-white/50 delay-75 duration-200">
            Ask about terrain, viewpoints, or anything
          </p>
        </div>
      </div>
      <div className="grid w-full grid-cols-2 gap-2 pb-4">
        <ThreadPrimitive.Suggestions
          components={{ Suggestion: SuggestionItem }}
        />
      </div>
    </div>
  );
}

const SuggestionItem: FC = () => {
  return (
    <div className="animate-in fade-in slide-in-from-bottom-2 fill-mode-both duration-200">
      <SuggestionPrimitive.Trigger send asChild>
        <PromptSuggestion
          className="h-auto w-full flex-col items-start justify-start gap-0.5 rounded-2xl border border-white/[0.08] bg-transparent px-4 py-3 text-left text-sm transition-colors hover:bg-white/[0.04]"
        >
          <span className="font-medium text-white/80">
            <SuggestionPrimitive.Title />
          </span>
          <span className="text-white/40">
            <SuggestionPrimitive.Description />
          </span>
        </PromptSuggestion>
      </SuggestionPrimitive.Trigger>
    </div>
  );
};
