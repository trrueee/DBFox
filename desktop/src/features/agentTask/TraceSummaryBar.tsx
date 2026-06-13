import { CheckCircle2, XCircle, ChevronDown, ChevronRight, Clock, Wrench, Layers, Database, AlertTriangle } from "lucide-react";
import type { AgentTabStatus } from "../../mock/databoxMock";
import type { AgentTaskSummary } from "./types";

interface TraceSummaryBarProps {
  summary: AgentTaskSummary;
  status: AgentTabStatus | "idle";
  expanded: boolean;
  onToggle: () => void;
}

function formatLatency(ms: number): string {
  if (ms >= 60000) return `${(ms / 60000).toFixed(1)}min`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.max(0, Math.round(ms))}ms`;
}

export function TraceSummaryBar({ summary, status, expanded, onToggle }: TraceSummaryBarProps) {
  const isFailed = status === "failed";
  const isDone = status === "completed" || isFailed;

  return (
    <div className="task-trace-summary" onClick={onToggle} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onToggle()}>
      {/* Status indicator */}
      {isDone ? (
        isFailed ? (
          <XCircle size={14} className="text-red-500 flex-shrink-0" />
        ) : (
          <CheckCircle2 size={14} className="text-green-500 flex-shrink-0" />
        )
      ) : (
        <AlertTriangle size={14} className="text-amber-500 flex-shrink-0" />
      )}

      {/* Status text */}
      <span className="task-trace-summary-status">
        {isFailed ? "运行中断" : "已完成"}
      </span>

      {/* Step count */}
      <span className="task-trace-summary-stat">
        <Layers size={10} />
        <span>{summary.totalSteps} 步</span>
      </span>

      {/* Tool count */}
      <span className="task-trace-summary-stat">
        <Wrench size={10} />
        <span>{summary.toolCount} 次工具调用</span>
      </span>

      {/* Query count */}
      {summary.queryCount > 0 && (
        <span className="task-trace-summary-stat">
          <Database size={10} />
          <span>{summary.queryCount} 次查询</span>
        </span>
      )}

      {/* Row count */}
      {typeof summary.rowCount === "number" && summary.rowCount > 0 && (
        <span className="task-trace-summary-stat">
          <span className="tabular-nums">{summary.rowCount.toLocaleString()} 行</span>
        </span>
      )}

      {/* Total latency */}
      {typeof summary.totalLatencyMs === "number" && summary.totalLatencyMs > 0 && (
        <span className="task-trace-summary-stat">
          <Clock size={10} />
          <span className="tabular-nums">{formatLatency(summary.totalLatencyMs)}</span>
        </span>
      )}

      {/* Expand chevron */}
      <span className="task-trace-summary-chevron">
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </span>
    </div>
  );
}
