"use client";

import { useRef, useEffect, type ReactNode } from "react";
import type { ChatMessage } from "@/types/chat";
import { MessageBubble } from "./message-bubble";
import styles from "@/app/chat-v2/chat-v2.module.css";

interface MessageListProps {
  messages: ChatMessage[];
  children?: ReactNode; // slot for thinking indicator
}

export function MessageList({ messages, children }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, children]);

  return (
    <div className={styles.messageList}>
      {(() => {
        let precedingUserMessage: string | undefined;
        return messages.map((msg) => {
          if (msg.role === "user") {
            precedingUserMessage = msg.content;
          }
          return (
            <MessageBubble
              key={msg.id}
              message={msg}
              precedingUserMessage={precedingUserMessage}
            />
          );
        });
      })()}
      {children}
      <div ref={bottomRef} />
    </div>
  );
}
