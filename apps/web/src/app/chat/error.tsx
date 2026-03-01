"use client";

export default function ChatError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        background: "#111",
        color: "#e0e0e0",
        gap: 16,
      }}
    >
      <h2 style={{ fontSize: 18, fontWeight: 600 }}>Something went wrong</h2>
      <p style={{ fontSize: 14, color: "#888", maxWidth: 400, textAlign: "center" }}>
        {error.message}
      </p>
      <button
        onClick={reset}
        style={{
          padding: "8px 16px",
          borderRadius: 8,
          border: "1px solid #444",
          background: "#222",
          color: "#e0e0e0",
          fontSize: 14,
          cursor: "pointer",
        }}
      >
        Try again
      </button>
    </div>
  );
}
