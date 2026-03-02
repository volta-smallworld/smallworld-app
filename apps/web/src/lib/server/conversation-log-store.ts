/**
 * Persistent NDJSON storage for chat conversation logs.
 *
 * One file per session at `.logs/conversations/{sessionId}.ndjson`.
 * Follows the same patterns as tool-log-store.ts: serialized write queue,
 * ensureDir cache, never-throw wrappers.
 *
 * Server-only module (Next.js server runtime).
 */

import * as fs from "fs/promises";
import * as path from "path";

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------

export interface ConversationLogRecord {
  id: string;
  sessionId: string;
  requestId: string;
  timestamp: string;
  userMessage: string;
  assistantResponse: string;
  toolRuns: Array<{ toolName: string; durationMs: number; isError: boolean }>;
  usage: { inputTokens: number; outputTokens: number };
  durationMs: number;
}

// ---------------------------------------------------------------------------
// Environment-driven configuration
// ---------------------------------------------------------------------------

const DEFAULT_MAX_RECORDS = 500;

function getLogDir(): string {
  return (
    process.env.CONVERSATION_LOG_PATH ??
    path.join(process.cwd(), ".logs", "conversations")
  );
}

function getMaxRecords(): number {
  const raw = process.env.CONVERSATION_LOG_MAX_RECORDS;
  if (raw) {
    const parsed = parseInt(raw, 10);
    if (!Number.isNaN(parsed) && parsed > 0) return parsed;
  }
  return DEFAULT_MAX_RECORDS;
}

export function isConversationLoggingEnabled(): boolean {
  const env = process.env.CONVERSATION_LOGGING_ENABLED;
  if (env !== undefined) {
    return env === "true" || env === "1";
  }
  return process.env.NODE_ENV !== "production";
}

// ---------------------------------------------------------------------------
// Directory existence cache
// ---------------------------------------------------------------------------

let dirEnsured = false;

async function ensureLogDir(): Promise<void> {
  if (dirEnsured) return;
  await fs.mkdir(getLogDir(), { recursive: true });
  dirEnsured = true;
}

// ---------------------------------------------------------------------------
// Serialized write queue (per session)
// ---------------------------------------------------------------------------

const writeQueues = new Map<string, Promise<void>>();

function enqueue(sessionId: string, fn: () => Promise<void>): Promise<void> {
  const prev = writeQueues.get(sessionId) ?? Promise.resolve();
  const next = prev.then(fn).catch((err) => {
    console.warn("[conversation-log-store] queued write failed:", err);
  });
  writeQueues.set(sessionId, next);
  return next;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Append a single conversation log record to the session's NDJSON file.
 *
 * - Creates the `.logs/conversations` directory if it does not exist.
 * - Serializes writes per session ID through a promise-chain queue.
 * - Enforces rolling retention after each write.
 * - Never throws.
 */
export async function appendConversationLog(
  record: ConversationLogRecord,
): Promise<void> {
  if (!isConversationLoggingEnabled()) return;

  try {
    await enqueue(record.sessionId, async () => {
      await ensureLogDir();

      const filePath = path.join(getLogDir(), `${record.sessionId}.ndjson`);
      const line = JSON.stringify(record) + "\n";
      await fs.appendFile(filePath, line, "utf-8");

      await enforceRetention(filePath);
    });
  } catch (err) {
    console.warn("[conversation-log-store] appendConversationLog failed:", err);
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function enforceRetention(filePath: string): Promise<void> {
  const maxRecords = getMaxRecords();

  let content: string;
  try {
    content = await fs.readFile(filePath, "utf-8");
  } catch {
    return;
  }

  const lines = content.trim().split("\n").filter(Boolean);

  if (lines.length <= maxRecords) return;

  const kept = lines.slice(lines.length - maxRecords);
  await fs.writeFile(filePath, kept.join("\n") + "\n", "utf-8");
}
