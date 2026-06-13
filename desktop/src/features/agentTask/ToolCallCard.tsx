import { useState, useMemo } from "react";
import { Wrench, ChevronDown, ChevronRight, Clock, CheckCircle2, XCircle, Loader2, Database, Search, Eye, Table2, RefreshCw, FileSearch, BarChart3 } from "lucide-react";
import type { ToolCallData } from "./types";

interface ToolCallCardProps {
  data: ToolCallData;
  isLatest?: boolean;
}

const TOOL_ICONS: Record<string, React.ReactNode> = {
  "db.query": <Database size={12} />,
  "query_database": <Database size={12} />,
  "execute_sql": <Database size={12} />,
  "db.preview": <Eye size={12} />,
  "preview_table": <Eye size={12} />,
  "db.inspect": <Search size={12} />,
  "inspect_database": <Search size={12} />,
  "schema.describe_table": <Table2 size={12} />,
  "describe_table": <Table2 size={12} />,
  "schema.list_tables": <FileSearch size={12} />,
  "list_tables": <FileSearch size={12} />,
  "schema.refresh_catalog": <RefreshCw size={12} />,
  "refresh_catalog": <RefreshCw size={12} />,
  "db.search": <Search size={12} />,
  "search_database": <Search size={12} />,
  "db.observe": <Eye size={12} />,
  "observe_database": <Eye size={12} />,
};

function getToolIcon(toolName: string): React.ReactNode {
  const normalized = toolName?.toLowerCase().replace(/[_-]/g, ".") || "";
  // Try exact match first
  for (const [key, icon] of Object.entries(TOOL_ICONS)) {
    if (key === normalized || key === toolName) return icon;
  }
  // Fuzzy match
  if (/query|sql|execute/.test(normalized)) return <Database size={12} />;
  if (/preview/.test(normalized)) return <Eye size={12} />;
  if (/inspect|describe|schema/.test(normalized)) return <Table2 size={12} />;
  if (/search/.test(normalized)) return <Search size={12} />;
  if (/chart|visualize/.test(normalized)) return <BarChart3 size={12} />;
  return <Wrench size={12} />;
}

function formatLatency(ms: number): string {
  if (ms >= 60000) return `${(ms / 60000).toFixed(1)}min`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.max(0, Math.round(ms))}ms`;
}

function formatJson(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function ToolCallCard({ data, isLatest = false }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(data.status === "failed");
  const hasDetail = Boolean(data.input || data.output || data.error);

  const statusBorder = useMemo(() => {
    if (data.status === "running") return "border-l-indigo-500";
    if (data.status === "failed") return "border-l-red-500";
    if (data.status === "success") return "border-l-green-500";
    return "border-l-slate-300";
  }, [data.status]);

  const statusDot = useMemo(() => {
    if (data.status === "running") {
      return (
        <span className="task-tool-dot task-tool-dot-running">
          <Loader2 size={10} className="animate-spin" />
        </span>
      );
    }
    if (data.status === "failed") {
      return <XCircle size={12} className="text-red-500" />;
    }
    if (data.status === "success") {
      return <CheckCircle2 size={12} className="text-green-500" />;
    }
    return <Wrench size={12} className="text-slate-400" />;
  }, [data.status]);

  const isPulsing = data.status === "running" && isLatest;

  return (
    <div className="task-trace-row">
      {/* Rail dot */}
      <div className={`task-trace-dot ${isPulsing ? "task-trace-dot-pulse" : ""}`}>
        {statusDot}
      </div>

      {/* Card body */}
      <div className={`task-tool-card ${statusBorder} ${data.status === "running" ? "task-tool-card-running" : ""} ${isPulsing ? "task-tool-card-shimmer" : ""}`}>
        {/* Header */}
        <button
          className="task-tool-card-header"
          onClick={() => hasDetail && setExpanded((v) => !v)}
          disabled={!hasDetail}
          type="button"
        >
          <span className="task-tool-icon">
            {getToolIcon(data.toolName)}
          </span>
          <span className="task-tool-name">{data.title || data.toolName}</span>
          {data.subtitle && (
            <span className="task-tool-subtitle">{data.subtitle}</span>
          )}
          <span className="task-tool-status-tag">
            {data.status === "running" ? "执行中" : data.status === "failed" ? "失败" : data.status === "success" ? "成功" : "跳过"}
          </span>
          {typeof data.latencyMs === "number" && data.latencyMs > 0 && (
            <span className="task-tool-latency">
              <Clock size={9} />
              {formatLatency(data.latencyMs)}
            </span>
          )}
          {hasDetail && (
            <span className="task-tool-expand">
              {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </span>
          )}
        </button>

        {/* Detail panel */}
        {hasDetail && expanded && (
          <div className="task-tool-detail">
            {data.input && (
              <div className="task-json-block">
                <div className="task-json-title">Input</div>
                <pre className="task-json-pre">{formatJson(data.input)}</pre>
              </div>
            )}
            {data.output && (
              <div className="task-json-block">
                <div className="task-json-title">Output</div>
                <pre className="task-json-pre">{formatJson(data.output)}</pre>
              </div>
            )}
            {data.error && (
              <div className="task-json-block task-json-danger">
                <div className="task-json-title">Error</div>
                <pre className="task-json-pre">{formatJson(data.error)}</pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
