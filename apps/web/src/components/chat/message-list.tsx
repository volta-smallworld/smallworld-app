import { useEffect, useRef } from "react";
import type { ChatMessage, ToolRun } from "@/types/chat";
import { ChatMessageBubble } from "./chat-message-bubble";
import styles from "@/app/chat/chat.module.css";

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  onToolClick: (runs: ToolRun[]) => void;
  activeTools?: Array<{ toolName: string }>;
}

export function MessageList({ messages, isLoading, error, onToolClick, activeTools = [] }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages, isLoading, activeTools]);

  return (
    <div className={styles.messages} ref={containerRef}>
      {messages.map((msg) => (
        <ChatMessageBubble key={msg.id} message={msg} onToolClick={onToolClick} />
      ))}
      {isLoading && (
        <div className={styles.loading}>
          <span className={styles.dot} />
          <span className={styles.dot} />
          <span className={styles.dot} />
          {activeTools.length > 0
            ? `Running: ${activeTools.map((t) => t.toolName).join(", ")}`
            : "Thinking..."}
        </div>
      )}
      {error && (
        <div className={`${styles.message} ${styles.assistantMessage} ${styles.errorText}`}>
          Error: {error}
        </div>
      )}
    </div>
  );
}
