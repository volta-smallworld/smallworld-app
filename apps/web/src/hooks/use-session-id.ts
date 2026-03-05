"use client";

import { useState, useCallback, useEffect } from "react";

export function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for non-secure contexts (HTTP over IP, etc.)
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * Generates a stable session ID per component mount.
 * Call `resetSessionId()` to rotate (e.g. on "New Chat").
 *
 * Initializes as empty string to avoid SSR/client hydration mismatch
 * (crypto.randomUUID() produces different values on server vs client).
 */
export function useSessionId() {
  const [sessionId, setSessionId] = useState("");

  useEffect(() => {
    setSessionId(generateId());
  }, []);

  const resetSessionId = useCallback(() => {
    setSessionId(generateId());
  }, []);

  return { sessionId, resetSessionId };
}
