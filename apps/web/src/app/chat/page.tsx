"use client";

import { useState, useCallback, useEffect } from "react";
import type { ChatMessage, ToolRun, StreamEvent } from "@/types/chat";
import { ChatHeader } from "@/components/chat/chat-header";
import { MessageList } from "@/components/chat/message-list";
import { ChatComposer } from "@/components/chat/chat-composer";
import { ToolInspector } from "@/components/chat/tool-inspector";
import { generateId } from "@/hooks/use-session-id";
import styles from "./chat.module.css";

const STORAGE_KEY = "smallworld-chat-history";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedToolRuns, setSelectedToolRuns] = useState<ToolRun[] | null>(null);
  const [activeTools, setActiveTools] = useState<Array<{ toolName: string }>>([]);

  // Load messages from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setMessages(JSON.parse(stored) as ChatMessage[]);
    } catch {
      // Ignore parse errors, start fresh
    }
  }, []);

  // Save messages to localStorage whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
      } catch {
        // Ignore storage errors
      }
    }
  }, [messages]);

  const handleSend = useCallback(
    async (text: string) => {
      if (isLoading) return;

      const userMessage: ChatMessage = {
        id: generateId(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };

      // Add a pending assistant message immediately
      const assistantId = generateId();
      const pendingAssistant: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        toolRuns: [],
      };

      const updatedMessages = [...messages, userMessage];
      setMessages([...updatedMessages, pendingAssistant]);
      setIsLoading(true);
      setError(null);
      setActiveTools([]);
      let accumulatedContent = "";
      const accumulatedToolRuns: ToolRun[] = [];

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: updatedMessages, stream: true }),
        });

        if (!res.ok || !res.body) {
          let errorMsg = res.statusText;
          try {
            const errBody = await res.json();
            errorMsg = errBody.error ?? errorMsg;
          } catch { /* use statusText */ }
          // Remove the pending assistant message on error
          setMessages(updatedMessages);
          setError(errorMsg);
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          // Keep the last potentially incomplete line in the buffer
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const json = line.slice(6);
            if (!json) continue;

            let event: StreamEvent;
            try {
              event = JSON.parse(json) as StreamEvent;
            } catch {
              continue;
            }

            switch (event.type) {
              case "text_delta":
                accumulatedContent += event.delta;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: accumulatedContent } : m
                  )
                );
                break;

              case "tool_start":
                setActiveTools((prev) => [...prev, { toolName: event.toolName }]);
                break;

              case "tool_end": {
                setActiveTools((prev) =>
                  prev.filter((t) => t.toolName !== event.toolName)
                );
                const toolRun: ToolRun = {
                  toolName: event.toolName,
                  input: {},
                  output: event.output,
                  isError: event.isError,
                  errorMessage: event.errorMessage,
                  durationMs: event.durationMs,
                  startedAt: event.startedAt,
                };
                accumulatedToolRuns.push(toolRun);
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, toolRuns: [...accumulatedToolRuns] }
                      : m
                  )
                );
                break;
              }

              case "done":
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          content: event.content,
                          toolRuns: event.toolRuns,
                        }
                      : m
                  )
                );
                setActiveTools([]);
                break;

              case "error":
                if (!accumulatedContent && accumulatedToolRuns.length === 0) {
                  setMessages(updatedMessages);
                }
                setError(event.message);
                break;

              case "status":
                // Status messages shown via activeTools indicator
                break;
            }
          }
        }
      } catch (err) {
        if (!accumulatedContent && accumulatedToolRuns.length === 0) {
          setMessages(updatedMessages);
        }
        setError(err instanceof Error ? err.message : "Network error");
      } finally {
        setIsLoading(false);
        setActiveTools([]);
      }
    },
    [isLoading, messages]
  );

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setError(null);
    setSelectedToolRuns(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore storage errors
    }
  }, []);

  const handleToolClick = useCallback((runs: ToolRun[]) => {
    setSelectedToolRuns(runs);
  }, []);

  return (
    <div className={styles.container}>
      <div className={styles.chatPanel}>
        <ChatHeader onNewChat={handleNewChat} />
        <MessageList
          messages={messages}
          isLoading={isLoading}
          error={error}
          onToolClick={handleToolClick}
          activeTools={activeTools}
        />
        <ChatComposer onSend={handleSend} isLoading={isLoading} />
      </div>
      <ToolInspector selectedToolRuns={selectedToolRuns} />
    </div>
  );
}
