/**
 * Utility for masking sensitive values in tool call log data before
 * writing to file or returning via API.
 *
 * Server-only module (Next.js server runtime).
 */

const REDACTED = "[REDACTED]";
const REDACTED_ERROR = "[REDACTED_ERROR]";

/**
 * Pattern matching common sensitive key names.
 * Exported for testing.
 */
export const SENSITIVE_KEY_PATTERN =
  /api[_-]?key|token|secret|authorization|password|cookie/i;

/**
 * Pattern matching bearer tokens and similar header-style secrets in plain text.
 * Covers:
 *   - Bearer <token>
 *   - Basic <base64>
 *   - Token <value>
 */
const BEARER_PATTERN = /\b(Bearer|Basic|Token)\s+\S+/gi;

/**
 * Masks bearer tokens and similar secret strings found in plain text.
 *
 * Example:
 *   "Authorization: Bearer eyJhbc..." -> "Authorization: Bearer [REDACTED]"
 */
export function maskSecretStrings(text: string): string {
  try {
    return text.replace(BEARER_PATTERN, (_match, scheme: string) => {
      return `${scheme} ${REDACTED}`;
    });
  } catch {
    return REDACTED_ERROR;
  }
}

/**
 * Recursively traverses objects and arrays, masking sensitive values while
 * preserving structure and non-sensitive fields for debugging context.
 *
 * - Keys matching `SENSITIVE_KEY_PATTERN` have their values replaced with "[REDACTED]".
 * - String values are scanned for bearer/header-style secrets via `maskSecretStrings`.
 * - Circular references are handled safely via a WeakSet of visited objects.
 * - Never throws; falls back to "[REDACTED_ERROR]" on failure.
 */
export function sanitizeForToolLog(value: unknown): unknown {
  try {
    return sanitize(value, new WeakSet());
  } catch {
    return REDACTED_ERROR;
  }
}

function sanitize(value: unknown, visited: WeakSet<object>): unknown {
  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === "string") {
    return maskSecretStrings(value);
  }

  if (typeof value !== "object") {
    // numbers, booleans, bigints, symbols, functions — pass through as-is
    return value;
  }

  // Guard against circular references
  if (visited.has(value as object)) {
    return REDACTED;
  }
  visited.add(value as object);

  if (Array.isArray(value)) {
    return value.map((item) => sanitize(item, visited));
  }

  // Plain objects (and class instances)
  const result: Record<string, unknown> = {};

  for (const key of Object.keys(value as Record<string, unknown>)) {
    const raw = (value as Record<string, unknown>)[key];

    if (SENSITIVE_KEY_PATTERN.test(key)) {
      result[key] = REDACTED;
    } else {
      result[key] = sanitize(raw, visited);
    }
  }

  return result;
}
