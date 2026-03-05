"use client";

import dynamic from "next/dynamic";
import { Composer } from "./composer";
import styles from "@/app/chat-v2/chat-v2.module.css";

const Orb = dynamic(
  () => import("./orb").then((m) => ({ default: m.Orb })),
  { ssr: false }
);

interface EmptyStateProps {
  onSend: (text: string) => void;
}

export function EmptyState({ onSend }: EmptyStateProps) {
  return (
    <>
      <div className={styles.emptyState}>
        <Orb
          size={250}
          speed={0.3}
          colorShift={0}
          className={styles.emptyOrbWrap}
        />
        <div>
          <h1 className={styles.greeting}>What can I help with?</h1>
          <p className={styles.greetingSub}>Ask about terrain, viewpoints, or anything</p>
        </div>
      </div>
      <Composer onSend={onSend} disabled={false} />
    </>
  );
}
