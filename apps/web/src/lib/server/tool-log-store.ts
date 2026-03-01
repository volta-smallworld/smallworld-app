/**
 * Persistent NDJSON storage for tool call debug logs.
 *
 * Writes one JSON record per line to a rolling log file on disk.
 * Reads, filters, and truncates logs for the debug UI / API.
 *
 * Server-only module (Next.js server runtime).
 */

import * as fs from "fs/promises";
import * as path from "path";
import { sanitizeForToolLog } from "@/lib/server/tool-log-redaction";

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------

export interface ToolLogRecord {
  id: string;
  eventType: "tool_discovery" | "tool_call";
  requestId: string;
  toolName: string;
  startedAt: string;
  endedAt: string;
  durationMs: number;
  isError: boolean;
  errorMessage?: string;
  input: unknown;
  output: string;
  metadata: { mcpServerUrl?: string; round?: number };
}

// ---------------------------------------------------------------------------
// Environment-driven configuration
// ---------------------------------------------------------------------------

const DEFAULT_MAX_ENTRIES = 2000;

function getLogPath(): string {
  return (
    process.env.TOOL_LOG_PATH ??
    path.join(process.cwd(), ".logs", "tool-calls.ndjson")
  );
}

function getMaxEntries(): number {
  const raw = process.env.TOOL_LOG_MAX_ENTRIES;
  if (raw) {
    const parsed = parseInt(raw, 10);
    if (!Number.isNaN(parsed) && parsed > 0) return parsed;
  }
  return DEFAULT_MAX_ENTRIES;
}

export function isToolLoggingEnabled(): boolean {
  const env = process.env.TOOL_LOGGING_ENABLED;
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
  const dir = path.dirname(getLogPath());
  await fs.mkdir(dir, { recursive: true });
  dirEnsured = true;
}

// ---------------------------------------------------------------------------
// Serialized write queue
// ---------------------------------------------------------------------------

let writeQueue: Promise<void> = Promise.resolve();

function enqueue(fn: () => Promise<void>): Promise<void> {
  writeQueue = writeQueue.then(fn).catch((err) => {
    console.warn("[tool-log-store] queued write failed:", err);
  });
  return writeQueue;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Append a single tool log record to the NDJSON file.
 *
 * - Sanitizes `input` and `output` through the redaction utility before writing.
 * - Creates the `.logs` directory if it does not exist.
 * - Serializes writes through a promise-chain queue to avoid concurrent corruption.
 * - Enforces rolling retention after each write.
 * - Never throws.
 */
export async function appendToolLog(record: ToolLogRecord): Promise<void> {
  if (!isToolLoggingEnabled()) return;

  try {
    await enqueue(async () => {
      await ensureLogDir();

      const sanitized: ToolLogRecord = {
        ...record,
        input: sanitizeForToolLog(record.input),
        output: sanitizeForToolLog(record.output) as string,
      };

      const line = JSON.stringify(sanitized) + "\n";
      await fs.appendFile(getLogPath(), line, "utf-8");

      // Enforce rolling retention
      await enforceRetention();
    });
  } catch (err) {
    console.warn("[tool-log-store] appendToolLog failed:", err);
  }
}

/**
 * Read and optionally filter log entries. Returns newest first.
 * If the log file does not exist, returns an empty array.
 */
export async function listToolLogs(
  filters?: { limit?: number; isError?: boolean; toolName?: string }
): Promise<ToolLogRecord[]> {
  try {
    const logPath = getLogPath();

    let content: string;
    try {
      content = await fs.readFile(logPath, "utf-8");
    } catch {
      // File doesn't exist or is unreadable
      return [];
    }

    const lines = content.trim().split("\n").filter(Boolean);
    let records: ToolLogRecord[] = [];

    for (const line of lines) {
      try {
        records.push(JSON.parse(line) as ToolLogRecord);
      } catch {
        // Skip malformed lines
      }
    }

    // Newest first
    records.reverse();

    // Apply filters
    if (filters?.isError !== undefined) {
      records = records.filter((r) => r.isError === filters.isError);
    }
    if (filters?.toolName !== undefined) {
      records = records.filter((r) => r.toolName === filters.toolName);
    }
    if (filters?.limit !== undefined && filters.limit > 0) {
      records = records.slice(0, filters.limit);
    }

    return records;
  } catch (err) {
    console.warn("[tool-log-store] listToolLogs failed:", err);
    return [];
  }
}

/**
 * Truncate / remove the log file. Never throws.
 */
export async function clearToolLogs(): Promise<void> {
  try {
    await fs.rm(getLogPath(), { force: true });
  } catch (err) {
    console.warn("[tool-log-store] clearToolLogs failed:", err);
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * If the log file exceeds `TOOL_LOG_MAX_ENTRIES` lines, keep only the
 * newest entries by rewriting the file.
 */
async function enforceRetention(): Promise<void> {
  const logPath = getLogPath();
  const maxEntries = getMaxEntries();

  let content: string;
  try {
    content = await fs.readFile(logPath, "utf-8");
  } catch {
    return;
  }

  const lines = content.trim().split("\n").filter(Boolean);

  if (lines.length <= maxEntries) return;

  // Keep only the newest (last) N lines
  const kept = lines.slice(lines.length - maxEntries);
  await fs.writeFile(logPath, kept.join("\n") + "\n", "utf-8");
}
