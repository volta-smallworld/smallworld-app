import Link from "next/link";
import styles from "@/app/chat/chat.module.css";

interface ChatHeaderProps {
  onNewChat: () => void;
}

export function ChatHeader({ onNewChat }: ChatHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <span className={styles.headerTitle}>Smallworld Chat</span>
        <button className={styles.newChatButton} onClick={onNewChat}>
          New Chat
        </button>
      </div>
      <Link href="/" className={styles.headerLink}>
        Back to Map
      </Link>
    </header>
  );
}
