"use client";

import dynamic from "next/dynamic";
import styles from "@/app/chat-v2/chat-v2.module.css";

const Orb = dynamic(
  () => import("./orb").then((m) => ({ default: m.Orb })),
  { ssr: false }
);

interface ThinkingIndicatorProps {
  activeToolName?: string;
}

export function ThinkingIndicator({ activeToolName }: ThinkingIndicatorProps) {
  return (
    <div className={styles.thinkingRow}>
      <Orb size={40} speed={1.2} colorShift={1} className={styles.thinkingOrb} />
      <span className={styles.thinkingLabel}>
        {activeToolName ? activeToolName : "Thinking..."}
      </span>
    </div>
  );
}
