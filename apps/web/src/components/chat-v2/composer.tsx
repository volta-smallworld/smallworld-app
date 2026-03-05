"use client";

import { useRef, useCallback } from "react";
import styles from "@/app/chat-v2/chat-v2.module.css";

interface ComposerProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function Composer({ onSend, disabled }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputRef = useRef("");

  const handleSend = useCallback(() => {
    const trimmed = inputRef.current.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    inputRef.current = "";
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
  }, [onSend, disabled]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      inputRef.current = e.target.value;
      const el = e.target;
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    },
    []
  );

  return (
    <div className={styles.composerWrap}>
      <div className={styles.composerInner}>
        <textarea
          ref={textareaRef}
          className={styles.composerTextarea}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Message..."
          rows={1}
          disabled={disabled}
        />
        <button
          className={styles.sendBtn}
          onClick={handleSend}
          disabled={disabled}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="19" x2="12" y2="5" />
            <polyline points="5 12 12 5 19 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
