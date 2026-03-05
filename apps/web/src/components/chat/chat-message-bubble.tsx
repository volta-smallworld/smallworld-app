import Image from "next/image";
import ReactMarkdown from "react-markdown";
import type { ChatMessage, ToolRun } from "@/types/chat";
import styles from "@/app/chat/chat.module.css";

/** Extract preview image URLs from tool run outputs. */
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

/** Select the single preview image URL that should be shown for this message. */
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

interface ChatMessageBubbleProps {
  message: ChatMessage;
  onToolClick: (runs: ToolRun[]) => void;
  precedingUserMessage?: string;
}

export function ChatMessageBubble({
  message,
  onToolClick,
  precedingUserMessage,
}: ChatMessageBubbleProps) {
  const previewImage =
    message.role === "assistant"
      ? extractPreviewImage(
          message.toolRuns,
          didUserRequestRawPreview(precedingUserMessage)
        )
      : null;

  return (
    <div className={`${styles.messageGroup} ${
      message.role === "user" ? styles.messageGroupUser : styles.messageGroupAssistant
    }`}>
      <div
        className={`${styles.message} ${
          message.role === "user" ? styles.userMessage : styles.assistantMessage
        }`}
      >
        {message.role === "assistant" ? (
          <div className={styles.markdown}>
            <ReactMarkdown
              components={{
                img: () => null,
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        ) : (
          message.content
        )}
        {message.toolRuns && message.toolRuns.length > 0 && (
          <div>
            <span
              className={styles.toolBadge}
              onClick={() => onToolClick(message.toolRuns!)}
            >
              {message.toolRuns.length} tool{message.toolRuns.length > 1 ? "s" : ""} used
            </span>
          </div>
        )}
      </div>
      {previewImage && (
        <div className={styles.previewImages}>
          <Image
            src={previewImage}
            alt="Preview render"
            className={styles.previewImage}
            width={500}
            height={333}
            unoptimized
          />
        </div>
      )}
    </div>
  );
}
