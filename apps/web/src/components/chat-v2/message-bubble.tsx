"use client";

import { useState, useCallback } from "react";
import Image from "next/image";
import ReactMarkdown from "react-markdown";
import type { ChatMessage, ToolRun } from "@/types/chat";
import styles from "@/app/chat-v2/chat-v2.module.css";

function didUserRequestRawPreview(message?: string): boolean {
  if (!message) return false;
  const text = message.toLowerCase();
  return (
    /\braw\b/.test(text) ||
    /\bunenhanced\b/.test(text) ||
    /\boriginal\b/.test(text) ||
    /without enhancement/.test(text) ||
    /no enhancement/.test(text)
  );
}

function extractPreviewImage(
  toolRuns: ToolRun[] | undefined,
  allowRaw: boolean
): string | null {
  if (!toolRuns || toolRuns.length === 0) return null;

  for (let i = toolRuns.length - 1; i >= 0; i -= 1) {
    const run = toolRuns[i];
    if (run.toolName !== "preview_render_pose" || run.isError) continue;

    try {
      const data = JSON.parse(run.output);
      const previewId = data.id as string | undefined;
      if (!previewId) continue;

      const hasRaw = Boolean(data.raw_image);
      const hasEnhanced = Boolean(data.enhanced_image);

      if (allowRaw) {
        if (hasRaw) {
          return `/api/previews/${previewId}/raw`;
        }
        continue;
      }
      if (hasEnhanced) {
        return `/api/previews/${previewId}/enhanced`;
      }
    } catch {
      // not JSON, skip
    }
  }

  return null;
}

interface MessageBubbleProps {
  message: ChatMessage;
  precedingUserMessage?: string;
}

export function MessageBubble({
  message,
  precedingUserMessage,
}: MessageBubbleProps) {
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);

  const openLightbox = useCallback((src: string) => setLightboxSrc(src), []);
  const closeLightbox = useCallback(() => setLightboxSrc(null), []);

  if (message.role === "user") {
    return (
      <div className={`${styles.messageRow} ${styles.messageRowUser}`}>
        <div className={styles.bubbleUser}>{message.content}</div>
      </div>
    );
  }

  const userRequestedRaw = didUserRequestRawPreview(precedingUserMessage);
  const previewImage = extractPreviewImage(message.toolRuns, userRequestedRaw);

  return (
    <>
      <div className={`${styles.messageRow} ${styles.messageRowAssistant}`}>
        <div className={styles.assistantGroup}>
          <div className={styles.bubbleAssistant}>
            <ReactMarkdown
              components={{
                img: () => null,
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
          {previewImage && (
            <div className={styles.previewImages}>
              <button
                type="button"
                className={styles.previewImageBtn}
                onClick={() => openLightbox(previewImage)}
              >
                <Image
                  src={previewImage}
                  alt="Preview render"
                  className={styles.previewImage}
                  width={500}
                  height={333}
                  unoptimized
                />
              </button>
            </div>
          )}
        </div>
      </div>

      {lightboxSrc && (
        <div className={styles.lightbox} onClick={closeLightbox}>
          <img
            src={lightboxSrc}
            alt="Preview render (full)"
            className={styles.lightboxImage}
          />
        </div>
      )}
    </>
  );
}
