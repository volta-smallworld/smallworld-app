import Image from "next/image";
import ReactMarkdown from "react-markdown";
import type { ChatMessage, ToolRun } from "@/types/chat";
import styles from "@/app/chat/chat.module.css";

/** Extract preview image URLs from tool run outputs. */
function extractPreviewImages(toolRuns?: ToolRun[]): string[] {
  if (!toolRuns) return [];
  const urls: string[] = [];
  for (const run of toolRuns) {
    if (run.toolName !== "preview_render_pose" || run.isError) continue;
    try {
      const data = JSON.parse(run.output);
      const previewId = data.id as string | undefined;
      if (!previewId) continue;
      const variant = data.enhanced_image ? "enhanced" : "raw";
      urls.push(`/api/previews/${previewId}/${variant}`);
    } catch {
      // not JSON, skip
    }
  }
  return urls;
}

interface ChatMessageBubbleProps {
  message: ChatMessage;
  onToolClick: (runs: ToolRun[]) => void;
}

export function ChatMessageBubble({ message, onToolClick }: ChatMessageBubbleProps) {
  const previewImages =
    message.role === "assistant" ? extractPreviewImages(message.toolRuns) : [];

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
            <ReactMarkdown>{message.content}</ReactMarkdown>
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
      {previewImages.length > 0 && (
        <div className={styles.previewImages}>
          {previewImages.map((url, i) => (
            <Image
              key={i}
              src={url}
              alt="Preview render"
              className={styles.previewImage}
              width={500}
              height={333}
              unoptimized
            />
          ))}
        </div>
      )}
    </div>
  );
}
