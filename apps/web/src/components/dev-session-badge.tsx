"use client";

/**
 * Dev-only badge showing the current chat session ID.
 * Returns null in production builds.
 */
export function DevSessionBadge({ sessionId }: { sessionId: string }) {
  if (process.env.NODE_ENV === "production" || !sessionId) return null;

  return (
    <span
      title={sessionId}
      className="rounded bg-white/[0.08] px-1.5 py-0.5 font-mono text-[10px] text-white/40 select-all"
    >
      {sessionId.slice(0, 8)}
    </span>
  );
}
