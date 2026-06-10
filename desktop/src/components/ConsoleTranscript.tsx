import { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Copy,
  Download,
  FileText,
  Play,
  RefreshCw,
  Save,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { DataTable } from "./DataTable";
import { ChartPanel } from "./ChartPanel";
import { QueryActionPlanPreview } from "./QueryActionPlanPreview";
import { actionRegistry } from "../lib/query-actions";
import type { QueryPlan, QueryResult, TrustGateResult } from "../lib/api";

export type ConsoleBlock =
  | { id: string; type: "input"; sql: string; createdAt: number }
  | { id: string; type: "running"; sql: string; startedAt: number }
  | {
      id: string;
      type: "result";
      sql: string;
      result: QueryResult;
      chartConfig?: { enabled: boolean; type: string; x: string; y: string } | null;
      createdAt: number;
    }
  | { id: string; type: "error"; sql: string; message: string; createdAt: number }
  | { id: string; type: "export"; sql: string; format: string; message: string; createdAt: number }
  | { id: string; type: "explain"; sql: string; title: string; message: string; createdAt: number }
  | {
      id: string;
      type: "aiSql";
      sql: string;
      title: string;
      trustGate?: TrustGateResult;
      queryPlan?: QueryPlan;
      createdAt: number;
    };

interface ConsoleTranscriptProps {
  blocks: ConsoleBlock[];
  currentSql: string;
  onSqlChange: (sql: string) => void;
  onExecute: () => void;
  onFormat: () => void;
  onExplain: (sql?: string) => void;
  onInjectLimit: () => void;
  onAddExportDirective: () => void;
  onAiOptimize: (sql?: string) => void;
  onAiExplain: (sql?: string) => void;
  onAiFixError: (sql: string, message: string) => void;
  onGenerateChart: (sql: string) => void;
  onReExecute: (sql: string) => void;
  onSaveQuery: (sql: string) => void;
  onCancel: () => void;
  onClear?: () => void;
  isRunning: boolean;
  databaseName?: string;
  engineLabel?: string;
}

function copyText(text: string) {
  void navigator.clipboard.writeText(text);
}

function csvFromResult(result: QueryResult) {
  const escapeCsv = (value: unknown): string => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };

  const header = result.columns.map(escapeCsv).join(",");
  const body = result.rows
    .map((row) => result.columns.map((column) => escapeCsv(row[column])).join(","))
    .join("\n");
  return `\uFEFF${header}\n${body}`;
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function riskLabel(risk?: TrustGateResult["riskLevel"]) {
  if (risk === "danger") return "危险";
  if (risk === "warning") return "警告";
  return "安全";
}

function riskClass(risk?: TrustGateResult["riskLevel"]) {
  if (risk === "danger") return "bg-destructive/15 text-destructive";
  if (risk === "warning") return "bg-warning/15 text-warning";
  return "bg-success/15 text-success";
}

export const ConsoleTranscript: React.FC<ConsoleTranscriptProps> = ({
  blocks,
  currentSql,
  onSqlChange,
  onExecute,
  onFormat,
  onExplain,
  onInjectLimit,
  onAddExportDirective,
  onAiOptimize,
  onAiExplain,
  onAiFixError,
  onGenerateChart,
  onReExecute,
  onSaveQuery,
  onCancel,
  onClear,
  isRunning,
  databaseName,
  engineLabel,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [now, setNow] = useState(0);
  const isAtBottomRef = useRef(true);

  const prompt = useMemo(() => {
    if (engineLabel === "postgresql") return "postgres>";
    if (engineLabel === "sqlite") return "sqlite>";
    return "mysql>";
  }, [engineLabel]);

  const meta = `${databaseName || "未连接"} · ${engineLabel || "mysql"}`;
  const inputRows = Math.min(12, Math.max(1, currentSql.split("\n").length));

  // 1. DSL Autocomplete Matching and Filtering
  const currentMatch = useMemo(() => {
    if (!currentSql) return null;
    const lines = currentSql.split("\n");
    const lastLine = lines[lines.length - 1] ?? "";
    const match = lastLine.match(/@(\w*)$/);
    return match ? match[1].toLowerCase() : null;
  }, [currentSql]);

  const allDirectives = useMemo(
    () =>
      actionRegistry.allProcessors().map((processor) => ({
        name: `@${processor.name}`,
        usage: processor.meta.examples[0] || processor.meta.usage,
        desc: processor.meta.description,
        examples: processor.meta.examples,
      })),
    [],
  );

  const filteredDirectives = useMemo(() => {
    if (currentMatch === null) return [];
    return allDirectives.filter((d) => d.name.slice(1).startsWith(currentMatch));
  }, [currentMatch, allDirectives]);

  const handleSelectDirective = (usage: string) => {
    const lines = currentSql.split("\n");
    if (lines.length > 0) {
      const lastIdx = lines.length - 1;
      lines[lastIdx] = lines[lastIdx].replace(/@\w*$/, usage);
      onSqlChange(lines.join("\n"));
    } else {
      onSqlChange(usage);
    }
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  // 2. DSL Live Compilation Plan Preview
  const previewPlan = useMemo(() => {
    if (!currentSql.trim()) return null;
    try {
      return actionRegistry.previewPlan(currentSql);
    } catch {
      // Plan preview may fail silently
      return null;
    }
  }, [currentSql]);

  useEffect(() => {
    if (!blocks.some((block) => block.type === "running")) return;
    const timer = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(timer);
  }, [blocks]);

  useEffect(() => {
    if (!scrollRef.current || !isAtBottomRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [blocks, currentSql]);

  const handleScroll = () => {
    const node = scrollRef.current;
    if (!node) return;
    isAtBottomRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 48;
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (!isRunning && currentSql.trim()) onExecute();
    }
  };

  const renderInputToolbar = (sql: string) => (
    <div className="console-block-toolbar" aria-label="SQL history actions">
      <button onClick={() => copyText(sql)} title="复制 SQL">
        <Copy size={11} />
        复制 SQL
      </button>
      <button onClick={() => onReExecute(sql)} title="重新执行">
        <RefreshCw size={11} />
        重新执行
      </button>
      <button onClick={() => onExplain(sql)} title="Explain">
        <FileText size={11} />
        Explain
      </button>
      <button onClick={() => onAiOptimize(sql)} title="AI 优化">
        <Wand2 size={11} />
        AI 优化
      </button>
      <button onClick={() => onSaveQuery(sql)} title="保存查询">
        <Save size={11} />
        保存查询
      </button>
    </div>
  );

  const renderResultToolbar = (block: Extract<ConsoleBlock, { type: "result" }>) => (
    <div className="console-block-toolbar" aria-label="Result actions">
      <button
        onClick={() => copyText(JSON.stringify(block.result.rows, null, 2))}
        title="复制结果 JSON"
      >
        <Copy size={11} />
        复制
      </button>
      <button
        onClick={() =>
          downloadText(
            `databox_export_${new Date().toISOString().slice(0, 10)}.csv`,
            csvFromResult(block.result),
            "text/csv;charset=utf-8",
          )
        }
        title="导出 CSV"
      >
        <Download size={11} />
        导出
      </button>
      <button onClick={() => onGenerateChart(block.sql)} title="生成图表">
        <BarChart3 size={11} />
        生成图表
      </button>
      <button onClick={() => onAiExplain(block.sql)} title="AI 解读">
        <Sparkles size={11} />
        AI 解读
      </button>
      <button onClick={() => onSaveQuery(block.sql)} title="保存查询">
        <Save size={11} />
        保存查询
      </button>
      <button onClick={() => onReExecute(block.sql)} title="重新执行">
        <RefreshCw size={11} />
        重新执行
      </button>
    </div>
  );

  const renderErrorToolbar = (block: Extract<ConsoleBlock, { type: "error" }>) => (
    <div className="console-block-toolbar" aria-label="Error actions">
      <button onClick={() => copyText(block.message)} title="复制错误">
        <Copy size={11} />
        复制错误
      </button>
      <button onClick={() => onAiFixError(block.sql, block.message)} title="AI 修复">
        <Wand2 size={11} />
        AI 修复
      </button>
      <button onClick={() => onReExecute(block.sql)} title="重新执行">
        <RefreshCw size={11} />
        重新执行
      </button>
    </div>
  );

  const renderAiSqlBlock = (block: Extract<ConsoleBlock, { type: "aiSql" }>) => {
    const gate = block.trustGate;
    const plan = block.queryPlan;
    const warnings = [
      ...(gate?.schemaWarnings ?? []),
      ...(plan?.warnings ?? []),
    ];
    const metricSummary = plan?.metrics?.map((metric) => `${metric.name}: ${metric.expression}`).join(", ") || "无";
    const dimensionSummary = plan?.dimensions?.map((dimension) => {
      const transform = dimension.transform ? `${dimension.transform} ` : "";
      return `${dimension.name}: ${transform}${dimension.column}`;
    }).join(", ") || "无";

    return (
      <div key={block.id} className="console-block console-block-note">
        <span className="console-note-label">{block.title}</span>
        <div className="console-ai-safety">
          <div className="console-ai-safety-row">
            <span className={`status-badge ${riskClass(gate?.riskLevel)}`}>{riskLabel(gate?.riskLevel)}</span>
            <span className={`status-badge ${gate?.requiresConfirmation ? "status-badge-warning" : "status-badge-neutral"}`}>
              {gate?.requiresConfirmation ? "需要确认" : "无需确认"}
            </span>
            <span>{formatTime(block.createdAt)}</span>
          </div>
          {gate?.messages?.length ? (
            <ul>
              {gate.messages.map((message) => <li key={message}>{message}</li>)}
            </ul>
          ) : null}
          {warnings.length ? (
            <ul>
              {warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          ) : null}
          {plan && (
            <div className="console-ai-plan">
              <div>Plan: {plan.intent} · tables: {plan.tables.join(", ") || "无"}</div>
              <div>Metrics: {metricSummary}</div>
              <div>Dimensions: {dimensionSummary}</div>
            </div>
          )}
          <pre className="console-note-body">{block.sql}</pre>
        </div>
      </div>
    );
  };

  const renderBlock = (block: ConsoleBlock) => {
    switch (block.type) {
      case "input":
        return (
          <div key={block.id} className="console-block console-block-input">
            <span className="prompt-label">{prompt}</span>
            <pre className="console-sql">{block.sql}</pre>
            {renderInputToolbar(block.sql)}
          </div>
        );

      case "running": {
        const elapsed = (((now || block.startedAt) - block.startedAt) / 1000).toFixed(1);
        return (
          <div key={block.id} className="console-block console-block-running">
            <span>执行中... {elapsed}s</span>
            <button className="console-stop-button" onClick={onCancel}>
              <X size={11} />
              停止
            </button>
          </div>
        );
      }

      case "result":
        return (
          <div key={block.id} className="console-block console-block-result">
            <div className="console-result-meta">
              <span>
                {block.result.rowCount} 行 · {block.result.latencyMs}ms · {formatTime(block.createdAt)}
              </span>
              {renderResultToolbar(block)}
            </div>

            {block.chartConfig?.enabled && (
              <div style={{
                marginBottom: 16,
                padding: 12,
                background: "rgba(30, 30, 34, 0.4)",
                border: "1px solid rgba(255, 255, 255, 0.05)",
                borderRadius: 8,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8, fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  <Sparkles size={12} style={{ color: "#4A5BC0" }} />
                  <strong>@chart 自动分析可视化</strong>
                </div>
                <ChartPanel
                  columns={block.result.columns}
                  rows={block.result.rows}
                  initialType={block.chartConfig.type}
                  initialX={block.chartConfig.x}
                  initialY={block.chartConfig.y}
                />
              </div>
            )}

            <DataTable
              columns={block.result.columns}
              rows={block.result.rows}
              maxHeight="360px"
            />
          </div>
        );

      case "error":
        return (
          <div key={block.id} className="console-block console-block-error">
            <div className="console-error-line">
              <strong>ERROR</strong>
              <span>{block.message}</span>
            </div>
            {renderErrorToolbar(block)}
          </div>
        );

      case "export":
        return (
          <div key={block.id} className="console-block console-block-note">
            <span className="console-note-label">@export {block.format}</span>
            <span>{block.message}</span>
          </div>
        );

      case "explain":
        return (
          <div key={block.id} className="console-block console-block-note">
            <span className="console-note-label">{block.title}</span>
            <pre className="console-note-body">{block.message}</pre>
          </div>
        );

      case "aiSql":
        return renderAiSqlBlock(block);
    }
  };

  return (
    <div className="console-transcript">
      <div className="console-scroll" ref={scrollRef} onScroll={handleScroll}>
        <div className="console-meta">
          <span>{meta}</span>
          {onClear && blocks.length > 0 && (
            <button onClick={onClear} title="清屏">
              清屏
            </button>
          )}
        </div>

        {blocks.map(renderBlock)}

        {/* 1. Render Live DSL Execution Plan compilation preview */}
        <QueryActionPlanPreview plan={previewPlan} />

        <div className="console-prompt active" style={{ position: "relative" }}>
          {/* 2. Directive Autocomplete suggestion intellisense menu */}
          {filteredDirectives.length > 0 && (
            <div className="console-autocomplete-dropdown" style={{
              position: "absolute",
              bottom: "calc(100% + 8px)",
              left: 16,
              background: "rgba(22, 22, 26, 0.95)",
              backdropFilter: "blur(16px)",
              border: "1px solid rgba(45, 59, 140, 0.4)",
              borderRadius: 6,
              boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
              display: "flex",
              flexDirection: "column",
              zIndex: 1000,
              width: 340,
              maxHeight: 200,
              overflowY: "auto",
              padding: 4
            }}>
              <div style={{
                fontSize: "0.7rem",
                color: "rgba(255,255,255,0.4)",
                padding: "4px 8px 6px 8px",
                borderBottom: "1px solid rgba(255,255,255,0.05)"
              }}>
                SQL DSL 注解指令智能补全 (Directive Intellisense)
              </div>
              {filteredDirectives.map((dir, i) => (
                <button
                  key={i}
                  onClick={() => handleSelectDirective(dir.usage)}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-start",
                    padding: "6px 8px",
                    background: "none",
                    border: "none",
                    borderRadius: 4,
                    width: "100%",
                    textAlign: "left",
                    cursor: "pointer",
                    transition: "background 0.15s ease",
                    gap: 2
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = "rgba(45, 59, 140, 0.25)"}
                  onMouseLeave={(e) => e.currentTarget.style.background = "none"}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.8rem", color: "#A5B4FC", fontWeight: 600 }}>
                    <span>{dir.name}</span>
                    <span style={{ fontSize: "0.68rem", opacity: 0.6, fontWeight: 400, fontFamily: "Courier New" }}>{dir.usage}</span>
                  </div>
                  <div style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.6)" }}>{dir.desc}</div>
                </button>
              ))}
            </div>
          )}
          <span className="prompt-label">{prompt}</span>
          <textarea
            ref={inputRef}
            className="console-input"
            value={currentSql}
            onChange={(event) => onSqlChange(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={inputRows}
            spellCheck={false}
            autoCapitalize="off"
            autoComplete="off"
          />
          <div className="console-inline-toolbar" aria-label="Current SQL actions">
            {isRunning ? (
              <button className="danger" onClick={onCancel}>
                <X size={11} />
                停止
              </button>
            ) : (
              <button className="primary" onClick={onExecute} disabled={!currentSql.trim()}>
                <Play size={11} />
                执行
              </button>
            )}
            <button onClick={onFormat} disabled={!currentSql.trim() || isRunning}>
              格式化
            </button>
            <button onClick={() => onExplain()} disabled={!currentSql.trim() || isRunning}>
              Explain
            </button>
            <button onClick={onInjectLimit} disabled={!currentSql.trim() || isRunning}>
              加 LIMIT
            </button>
            <button onClick={onAddExportDirective} disabled={!currentSql.trim() || isRunning}>
              @export
            </button>
            <button onClick={() => onAiOptimize()} disabled={!currentSql.trim() || isRunning}>
              <Wand2 size={11} />
              AI 优化
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
