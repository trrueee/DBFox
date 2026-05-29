import { useRef, useEffect, useState, useCallback } from "react";
import { Play, Copy, Download, RefreshCw, X, RotateCcw } from "lucide-react";
import { DataTable } from "./DataTable";
import type { QueryResult } from "../lib/api";

// ═══════════════════════════════════════
// Console Block Types
// ═══════════════════════════════════════

export type ConsoleBlock =
  | { id: string; type: "input"; sql: string; createdAt: number }
  | { id: string; type: "running"; sql: string; startedAt: number }
  | { id: string; type: "result"; sql: string; result: QueryResult }
  | { id: string; type: "error"; sql: string; message: string };

interface ConsoleTranscriptProps {
  blocks: ConsoleBlock[];
  currentSql: string;
  onSqlChange: (sql: string) => void;
  onExecute: () => void;
  onFormat: () => void;
  onExplain: () => void;
  onInjectLimit: () => void;
  onCancel: () => void;
  onClear?: () => void;
  isRunning: boolean;
  databaseName?: string;
  engineLabel?: string;
}

export const ConsoleTranscript: React.FC<ConsoleTranscriptProps> = ({
  blocks,
  currentSql,
  onSqlChange,
  onExecute,
  onFormat,
  onExplain,
  onInjectLimit,
  onCancel,
  onClear,
  isRunning,
  databaseName,
  engineLabel,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [hoveredBlockId, setHoveredBlockId] = useState<string | null>(null);
  const isAtBottomRef = useRef(true);

  const prompt = engineLabel === "postgresql" ? "postgres>" : engineLabel === "sqlite" ? "sqlite>" : "mysql>";

  // Track whether user is at the bottom
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const el = scrollRef.current;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
  }, []);

  // Smart auto-scroll: only scroll if user was at the bottom
  useEffect(() => {
    if (!scrollRef.current || !isAtBottomRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [blocks, currentSql]);

  // Ctrl+Enter to execute
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (!isRunning && currentSql.trim()) onExecute();
    }
  };

  const renderBlockToolbar = (block: ConsoleBlock) => {
    if (hoveredBlockId !== block.id) return null;
    return (
      <div style={{ display: "flex", gap: 2, flexShrink: 0, paddingLeft: 8 }}>
        {block.type === "input" && (
          <>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => navigator.clipboard.writeText(block.sql)}><Copy size={9} /> 复制</button>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => { onSqlChange(block.sql); setTimeout(() => inputRef.current?.focus(), 50); }}>
              <RefreshCw size={9} /> 重新执行
            </button>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => { onSqlChange(block.sql); onExplain(); }}>
              Explain
            </button>
          </>
        )}
        {block.type === "result" && (
          <>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => {
                const json = JSON.stringify((block.result.rows as Record<string,unknown>[]).map((r) => {
                  const o: Record<string,unknown> = {};
                  block.result.columns.forEach((c) => o[c] = r[c] ?? null);
                  return o;
                }), null, 2);
                navigator.clipboard.writeText(json);
              }}><Copy size={9} /> JSON</button>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => {
                const cols = block.result.columns;
                const rows = block.result.rows as Record<string,unknown>[];
                const csv = "﻿" + cols.join(",") + "\n" + rows.map(r => cols.map(c => {
                  const v = r[c]; if (v === null) return ""; const s = String(v);
                  return s.includes(",") ? `"${s.replace(/"/g, '""')}"` : s;
                }).join(",")).join("\n");
                const blob = new Blob([csv], { type: "text/csv" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url; a.download = "export.csv"; a.click();
                URL.revokeObjectURL(url);
              }}><Download size={9} /> CSV</button>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => { onSqlChange(block.sql); setTimeout(() => { onExecute(); }, 50); }}>
              <RotateCcw size={9} /> 重新执行
            </button>
          </>
        )}
        {block.type === "error" && (
          <>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => navigator.clipboard.writeText(block.message)}><Copy size={9} /> 复制错误</button>
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.62rem" }}
              onClick={() => { onSqlChange(block.sql); setTimeout(() => { onExecute(); }, 50); }}>
              <RotateCcw size={9} /> 重新执行
            </button>
          </>
        )}
      </div>
    );
  };

  const promptGreen = "#2E7D32";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#fff", fontFamily: "var(--font-mono)" }}>
      {/* Connection bar — also houses the inline toolbar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "2px 10px",
        fontSize: "0.64rem", color: "var(--text-muted)", background: "var(--bg-secondary)",
        userSelect: "none", flexShrink: 0, fontFamily: "var(--font-body)", gap: 8,
      }}>
        <span style={{ whiteSpace: "nowrap" }}>
          <strong style={{ color: "var(--text-secondary)" }}>{databaseName || "(未连接)"}</strong>
          {engineLabel && <span style={{ opacity: 0.5 }}> · {engineLabel}</span>}
        </span>

        {/* Inline toolbar — in the header, not below prompt */}
        <div style={{ display: "flex", alignItems: "center", gap: 3, flexShrink: 0 }}>
          {isRunning ? (
            <button onClick={onCancel} style={{
              display: "inline-flex", alignItems: "center", gap: 2,
              padding: "1px 6px", fontSize: "0.6rem", fontWeight: 600,
              color: "var(--accent-red)", background: "var(--accent-red-light)",
              border: "1px solid var(--accent-red)", borderRadius: 2,
              cursor: "pointer", fontFamily: "var(--font-body)",
            }}><X size={9} /> 停止</button>
          ) : (
            <>
              <button onClick={onExecute} disabled={!currentSql.trim()} style={{
                display: "inline-flex", alignItems: "center", gap: 2,
                padding: "1px 8px", fontSize: "0.6rem", fontWeight: 600,
                color: "#fff", background: currentSql.trim() ? "var(--accent-primary)" : "var(--border-medium)",
                border: "none", borderRadius: 2, cursor: currentSql.trim() ? "pointer" : "default",
                fontFamily: "var(--font-body)",
              }}><Play size={9} /> 执行</button>
              <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.58rem" }}
                onClick={onFormat} disabled={!currentSql.trim()}>格式化</button>
              <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.58rem" }}
                onClick={onExplain} disabled={!currentSql.trim()}>Explain</button>
              <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.58rem" }}
                onClick={onInjectLimit} disabled={!currentSql.trim()}>加 LIMIT</button>
            </>
          )}
          {onClear && blocks.length > 0 && (
            <button className="btn-ghost" style={{ padding: "1px 4px", fontSize: "0.58rem", marginLeft: 4 }}
              onClick={onClear}>清屏</button>
          )}
        </div>
      </div>

      {/* Scrollable transcript — prompt is the last element in this flow */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "6px 0" }}
      >
        {/* Past blocks */}
        {blocks.map((block) => (
          <div
            key={block.id}
            onMouseEnter={() => setHoveredBlockId(block.id)}
            onMouseLeave={() => setHoveredBlockId(null)}
            style={{ padding: "0 12px" }}
          >
            {block.type === "input" && (
              <div style={{ padding: "2px 0", display: "flex", alignItems: "flex-start", gap: 6 }}>
                <span style={{ color: promptGreen, fontWeight: 600, fontSize: "0.72rem", userSelect: "none", whiteSpace: "nowrap", marginTop: 1 }}>
                  {prompt}
                </span>
                <pre style={{
                  margin: 0, flex: 1, whiteSpace: "pre-wrap", wordBreak: "break-all",
                  fontSize: "0.72rem", color: "var(--text-primary)", lineHeight: 1.5,
                  fontFamily: "var(--font-mono)",
                }}>
                  {block.sql}
                </pre>
                {renderBlockToolbar(block)}
              </div>
            )}

            {block.type === "running" && (
              <div style={{ padding: "2px 0 2px 20px", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: "var(--accent-primary)", fontSize: "0.66rem", fontFamily: "var(--font-body)" }}>
                  执行中...
                </span>
                <button onClick={onCancel} style={{
                  background: "none", color: "var(--accent-red)", border: "1px solid var(--accent-red)",
                  borderRadius: 2, padding: "0 5px", fontSize: "0.6rem", cursor: "pointer",
                  fontFamily: "var(--font-body)",
                }}>
                  取消
                </button>
              </div>
            )}

            {block.type === "result" && (
              <div style={{ padding: "0 0 4px", borderBottom: "1px solid var(--border-light)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1px 0" }}>
                  <span style={{ fontSize: "0.62rem", color: "var(--text-muted)", fontFamily: "var(--font-body)" }}>
                    {block.result.rowCount} 行 · {block.result.latencyMs}ms
                  </span>
                  {renderBlockToolbar(block)}
                </div>
                <DataTable
                  columns={block.result.columns}
                  rows={block.result.rows as Record<string,unknown>[]}
                  maxHeight="360px"
                />
              </div>
            )}

            {block.type === "error" && (
              <div style={{
                padding: "2px 0 4px", borderBottom: "1px solid var(--border-light)",
                color: "var(--accent-red)", fontSize: "0.66rem", fontFamily: "var(--font-body)",
              }}>
                <span style={{ fontWeight: 600 }}>ERROR </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.64rem" }}>{block.message}</span>
                {renderBlockToolbar(block)}
              </div>
            )}
          </div>
        ))}

        {/* Active prompt — last element in scroll flow */}
        <div style={{ padding: blocks.length === 0 ? "12px 12px" : "8px 12px 4px" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
            <span style={{
              color: promptGreen, fontWeight: 600, fontSize: "0.72rem",
              userSelect: "none", whiteSpace: "nowrap", marginTop: 3, lineHeight: 1.5,
            }}>
              {prompt}
            </span>
            <textarea
              ref={inputRef}
              value={currentSql}
              onChange={(e) => onSqlChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder=""
              rows={Math.max(2, currentSql.split("\n").length)}
              style={{
                flex: 1, border: "none", outline: "none", resize: "none",
                fontFamily: "var(--font-mono)", fontSize: "0.72rem",
                color: "var(--text-primary)", lineHeight: 1.5,
                background: "transparent", padding: 0,
                caretColor: "var(--accent-primary)",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
