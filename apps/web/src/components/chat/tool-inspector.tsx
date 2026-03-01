"use client";

import { useState, useCallback } from "react";
import type { ToolRun, ToolLogEntry, ToolLogsResponse } from "@/types/chat";
import styles from "@/app/chat/chat.module.css";

interface ToolInspectorProps {
  selectedToolRuns: ToolRun[] | null;
}

type Tab = "runs" | "logs";

export function ToolInspector({ selectedToolRuns }: ToolInspectorProps) {
  const [tab, setTab] = useState<Tab>("runs");
  const [logs, setLogs] = useState<ToolLogEntry[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [toolFilter, setToolFilter] = useState("");

  const fetchLogs = useCallback(async () => {
    setLogsLoading(true);
    setLogsError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (errorsOnly) params.set("isError", "true");
      if (toolFilter.trim()) params.set("toolName", toolFilter.trim());
      const res = await fetch(`/api/tool-logs?${params}`);
      if (!res.ok) {
        if (res.status === 404) {
          setLogsError("Tool logging is disabled");
          setLogs([]);
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const data: ToolLogsResponse = await res.json();
      setLogs(data.entries);
    } catch (err) {
      setLogsError(err instanceof Error ? err.message : String(err));
    } finally {
      setLogsLoading(false);
    }
  }, [errorsOnly, toolFilter]);

  const clearLogs = useCallback(async () => {
    try {
      await fetch("/api/tool-logs", { method: "DELETE" });
      setLogs([]);
    } catch {
      // ignore
    }
  }, []);

  const handleTabChange = (t: Tab) => {
    setTab(t);
    if (t === "logs" && logs.length === 0 && !logsLoading) {
      fetchLogs();
    }
  };

  return (
    <div className={styles.inspectorPanel}>
      <div className={styles.inspectorHeader}>
        <div className={styles.inspectorTabs}>
          <button
            className={`${styles.inspectorTab} ${tab === "runs" ? styles.inspectorTabActive : ""}`}
            onClick={() => handleTabChange("runs")}
          >
            Message Runs
          </button>
          <button
            className={`${styles.inspectorTab} ${tab === "logs" ? styles.inspectorTabActive : ""}`}
            onClick={() => handleTabChange("logs")}
          >
            Recent Logs
          </button>
        </div>
      </div>

      {tab === "runs" && (
        <>
          {!selectedToolRuns ? (
            <div className={styles.inspectorEmpty}>
              Click a tool badge to inspect execution details
            </div>
          ) : (
            selectedToolRuns.map((run, i) => (
              <div key={i} className={styles.toolRunItem}>
                <div className={styles.toolRunName}>{run.toolName}</div>
                <div className={styles.toolRunMeta}>
                  {run.durationMs}ms · {run.startedAt}
                </div>
                <div className={styles.toolRunSection}>
                  <div className={styles.toolRunLabel}>Input</div>
                  <pre className={styles.toolRunCode}>
                    {JSON.stringify(run.input, null, 2)}
                  </pre>
                </div>
                <div className={styles.toolRunSection}>
                  <div className={styles.toolRunLabel}>Output</div>
                  <pre
                    className={`${styles.toolRunCode} ${run.isError ? styles.toolRunError : ""}`}
                  >
                    {run.isError ? run.errorMessage : run.output}
                  </pre>
                </div>
              </div>
            ))
          )}
        </>
      )}

      {tab === "logs" && (
        <div className={styles.logsContainer}>
          <div className={styles.logsToolbar}>
            <label className={styles.logsCheckbox}>
              <input
                type="checkbox"
                checked={errorsOnly}
                onChange={(e) => setErrorsOnly(e.target.checked)}
              />
              Errors only
            </label>
            <input
              type="text"
              className={styles.logsFilterInput}
              placeholder="Filter by tool name..."
              value={toolFilter}
              onChange={(e) => setToolFilter(e.target.value)}
            />
            <button className={styles.logsButton} onClick={fetchLogs} disabled={logsLoading}>
              {logsLoading ? "Loading..." : "Refresh"}
            </button>
            <button className={styles.logsButtonDanger} onClick={clearLogs}>
              Clear
            </button>
          </div>

          {logsError && (
            <div className={styles.logsError}>{logsError}</div>
          )}

          {logs.length === 0 && !logsLoading && !logsError && (
            <div className={styles.inspectorEmpty}>No log entries found</div>
          )}

          {logs.map((entry) => (
            <div key={entry.id} className={styles.toolRunItem}>
              <div className={styles.toolRunName}>
                {entry.isError && <span className={styles.logErrorBadge}>ERR</span>}
                {entry.toolName}
                <span className={styles.logEventType}>{entry.eventType}</span>
              </div>
              <div className={styles.toolRunMeta}>
                {entry.durationMs}ms · {entry.startedAt} · req:{entry.requestId.slice(0, 8)}
              </div>
              <div className={styles.toolRunSection}>
                <div className={styles.toolRunLabel}>
                  Input{entry.inputTruncated && " (truncated)"}
                </div>
                <pre className={styles.toolRunCode}>{entry.inputPreview}</pre>
              </div>
              <div className={styles.toolRunSection}>
                <div className={styles.toolRunLabel}>
                  Output{entry.outputTruncated && " (truncated)"}
                </div>
                <pre
                  className={`${styles.toolRunCode} ${entry.isError ? styles.toolRunError : ""}`}
                >
                  {entry.isError ? entry.errorMessage ?? entry.outputPreview : entry.outputPreview}
                </pre>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
