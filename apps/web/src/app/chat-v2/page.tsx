"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { ChatMessage, ToolRun, StreamEvent } from "@/types/chat";
import { EmptyState } from "@/components/chat-v2/empty-state";
import { MessageList } from "@/components/chat-v2/message-list";
import { Composer } from "@/components/chat-v2/composer";
import { ThinkingIndicator } from "@/components/chat-v2/thinking-indicator";
import { useSessionId } from "@/hooks/use-session-id";
import { DevSessionBadge } from "@/components/dev-session-badge";
import styles from "./chat-v2.module.css";

const STORAGE_KEY = "smallworld-chat-v2-history";

type Phase = "empty" | "thinking" | "conversation";

export default function ChatV2Page() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [phase, setPhase] = useState<Phase>("empty");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeToolName, setActiveToolName] = useState<string | undefined>();
  const { sessionId, resetSessionId } = useSessionId();
  const columnRef = useRef<HTMLDivElement>(null);

  // Lock body scroll and track visual viewport height for mobile keyboard handling
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;

    // Lock body so iOS can't scroll it behind our fixed container
    html.style.overflow = "hidden";
    body.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.width = "100%";
    body.style.height = "100%";

    const vv = window.visualViewport;
    function syncHeight() {
      const h = vv ? vv.height : window.innerHeight;
      columnRef.current?.style.setProperty("height", `${h}px`);
    }

    if (vv) {
      vv.addEventListener("resize", syncHeight);
      vv.addEventListener("scroll", syncHeight);
    }
    syncHeight();

    return () => {
      html.style.overflow = "";
      body.style.overflow = "";
      body.style.position = "";
      body.style.width = "";
      body.style.height = "";
      if (vv) {
        vv.removeEventListener("resize", syncHeight);
        vv.removeEventListener("scroll", syncHeight);
      }
    };
  }, []);

  // Load messages from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as ChatMessage[];
        if (parsed.length > 0) {
          setMessages(parsed);
          setPhase("conversation");
        }
      }
    } catch {
      // Ignore parse errors
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
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };

      const assistantId = crypto.randomUUID();
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
      setPhase("thinking");
      setError(null);
      setActiveToolName(undefined);
      let accumulatedContent = "";
      const accumulatedToolRuns: ToolRun[] = [];
      let receivedFirstDelta = false;

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Session-Id": sessionId,
          },
          body: JSON.stringify({ messages: updatedMessages, stream: true }),
        });

        if (!res.ok || !res.body) {
          let errorMsg = res.statusText;
          try {
            const errBody = await res.json();
            errorMsg = errBody.error ?? errorMsg;
          } catch {
            /* use statusText */
          }
          setMessages(updatedMessages);
          setError(errorMsg);
          setPhase(updatedMessages.length > 0 ? "conversation" : "empty");
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
                if (!receivedFirstDelta) {
                  receivedFirstDelta = true;
                  setPhase("conversation");
                }
                accumulatedContent += event.delta;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: accumulatedContent }
                      : m
                  )
                );
                break;

              case "tool_start":
                setActiveToolName(event.toolName);
                break;

              case "tool_end": {
                setActiveToolName(undefined);
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
                setPhase("conversation");
                break;

              case "error":
                if (
                  !accumulatedContent &&
                  accumulatedToolRuns.length === 0
                ) {
                  setMessages(updatedMessages);
                }
                setError(event.message);
                setPhase(
                  updatedMessages.length > 0 ? "conversation" : "empty"
                );
                break;

              case "status":
                break;
            }
          }
        }
      } catch (err) {
        if (!accumulatedContent && accumulatedToolRuns.length === 0) {
          setMessages(updatedMessages);
        }
        setError(err instanceof Error ? err.message : "Network error");
        setPhase(updatedMessages.length > 0 ? "conversation" : "empty");
      } finally {
        setIsLoading(false);
        setActiveToolName(undefined);
        if (!receivedFirstDelta && messages.length === 0) {
          // Stayed in thinking without getting text — still show conversation
          // if we have messages from the user
        }
      }
    },
    [isLoading, messages, sessionId]
  );

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setPhase("empty");
    setError(null);
    resetSessionId();
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore storage errors
    }
  }, [resetSessionId]);

  return (
    <div className={styles.viewport}>
      <div ref={columnRef} className={styles.column}>
        {phase === "empty" ? (
          <EmptyState onSend={handleSend} />
        ) : (
          <>
            <div className={styles.header}>
              <span className={styles.headerTitle}>SmallWorld</span>
              <DevSessionBadge sessionId={sessionId} />
              <button className={styles.newChatBtn} onClick={handleNewChat}>
                New chat
              </button>
            </div>

            <MessageList messages={messages}>
              {isLoading && (
                <ThinkingIndicator activeToolName={activeToolName} />
              )}
            </MessageList>

            {error && <div className={styles.error}>{error}</div>}

            <Composer onSend={handleSend} disabled={isLoading} />
          </>
        )}
      </div>
    </div>
  );
}
