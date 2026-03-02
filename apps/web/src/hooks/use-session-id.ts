"use client";

import { useState, useCallback } from "react";

/**
 * Generates a stable session ID per component mount.
 * Call `resetSessionId()` to rotate (e.g. on "New Chat").
 */
export function useSessionId() {
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());

  const resetSessionId = useCallback(() => {
    setSessionId(crypto.randomUUID());
  }, []);

  return { sessionId, resetSessionId };
}
