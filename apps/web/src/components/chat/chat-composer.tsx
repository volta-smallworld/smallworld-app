import { useRef, useCallback } from "react";
import styles from "@/app/chat/chat.module.css";

interface ChatComposerProps {
  onSend: (text: string) => void;
  isLoading: boolean;
}

export function ChatComposer({ onSend, isLoading }: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputRef = useRef("");

  const handleSend = useCallback(() => {
    const trimmed = inputRef.current.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    inputRef.current = "";
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
  }, [onSend, isLoading]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    inputRef.current = e.target.value;
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  return (
    <div className={styles.composer}>
      <textarea
        ref={textareaRef}
        className={styles.input}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Ask about terrain, viewpoints..."
        rows={1}
        disabled={isLoading}
      />
      <button
        className={styles.sendButton}
        onClick={handleSend}
        disabled={isLoading}
      >
        Send
      </button>
    </div>
  );
}
