import { Activity, CheckCircle2, Circle, Database, MessageSquare, Search, ShieldCheck, Wrench, XCircle } from "lucide-react";
import type { AgentRuntimeEvent } from "../../../lib/api/types";
import type { ConversationRun } from "../../../types/conversation";

const TOOL_LABELS: Record<string, string> = {
  "db.observe": "浏览数据库结构",
  "db.search": "搜索相关表和字段",
  "db.inspect": "检查表结构",
  "db.preview": "预览样例数据",
  "sql.validate": "校验 SQL 安全性",
  "sql.execute_readonly": "执行只读查询",
  "chart.suggest": "生成图表建议",
  "answer.synthesize": "整理最终答案",
};

const EVENT_LABELS: Record<string, string> = {
  "agent.run.started": "开始执行任务",
  "agent.run.completed": "任务完成",
  "agent.run.failed": "执行失败",
  "agent.run.cancelled": "执行已取消",
  "agent.run.waiting_approval": "等待确认",
  "agent.approval.required": "需要确认",
  "agent.approval.resolved": "确认已处理",
  "agent.artifact.created": "生成数据产物",
  "agent.answer.completed": "整理最终答案",
};

export function RunTracePanel({ run }: { run: ConversationRun }) {
  const events = (run.events || []).filter((event) => String(event.type) !== "agent.answer.delta");
  const lastEvent = events[events.length - 1];
  const summary = runSummary(run, events, lastEvent);

  return (
    <details className="conv-run-trace" open={run.status === "running" || run.status === "failed"}>
      <summary>
        {run.status === "failed" ? <XCircle size={14} /> : <Activity size={14} />}
        <span>{summary}</span>
        {events.length > 0 && <span className="conv-run-count">{events.length}</span>}
      </summary>
      <div className="conv-run-trace-body">
        {events.length > 0 ? (
          <ol className="conv-run-events">
            {events.map((event) => (
              <li key={event.event_id || `${event.type}-${event.sequence}`}>
                <span className="conv-run-event-icon">{eventIcon(event)}</span>
                <span className="conv-run-event-copy">
                  <strong>{eventTitle(event)}</strong>
                  {eventSummary(event) && <span>{eventSummary(event)}</span>}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <div className="conv-run-empty">Waiting for runtime events...</div>
        )}
        <div className="conv-run-id">Run ID: {run.id}</div>
        {run.error_message && <div>{run.error_message}</div>}
      </div>
    </details>
  );
}

function runSummary(
  run: ConversationRun,
  events: AgentRuntimeEvent[],
  lastEvent: AgentRuntimeEvent | undefined,
): string {
  if (run.status === "running") return lastEvent ? eventTitle(lastEvent) : "DBFox 正在分析...";
  if (run.status === "failed") return "执行失败";
  if (run.status === "cancelled") return "执行已取消";
  if (run.status === "waiting_approval") return "等待确认";
  if (run.status !== "completed") return "执行过程";

  const sqlCount = events.filter((event) => toolName(event) === "sql.execute_readonly").length;
  const rowCount = sumNumeric(events, ["rowCount", "row_count", "rows"]);
  const durationMs = sumNumeric(events, ["durationMs", "duration_ms", "latencyMs", "latency_ms"]);
  const parts = [`执行过程`, `${events.length} 步`];
  if (sqlCount > 0) parts.push(`${sqlCount} 条 SQL`);
  if (rowCount > 0) parts.push(`${rowCount} 行`);
  if (durationMs > 0) parts.push(`${durationMs}ms`);
  return parts.join(" · ");
}

function stepValue(event: AgentRuntimeEvent, key: string): string {
  const value = event.step?.[key];
  return typeof value === "string" ? value : "";
}

function stepNumber(event: AgentRuntimeEvent, key: string): number {
  const value = event.step?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return 0;
}

function outputNumber(event: AgentRuntimeEvent, key: string): number {
  const output = event.step?.output;
  if (!output || typeof output !== "object") return 0;
  const value = (output as Record<string, unknown>)[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return 0;
}

function sumNumeric(events: AgentRuntimeEvent[], keys: string[]): number {
  return events.reduce((total, event) => {
    for (const key of keys) {
      const value = stepNumber(event, key) || outputNumber(event, key);
      if (value > 0) return total + value;
    }
    return total;
  }, 0);
}

function toolName(event: AgentRuntimeEvent): string {
  return stepValue(event, "tool_name") || stepValue(event, "tool");
}

function eventTitle(event: AgentRuntimeEvent): string {
  const tool = toolName(event);
  if (tool) return TOOL_LABELS[tool] || tool;
  const name = stepValue(event, "name") || stepValue(event, "step_name");
  if (name) return name;
  if (event.type === "agent.artifact.created") return event.artifact?.title || "Artifact created";
  return EVENT_LABELS[String(event.type)] || String(event.type).replace("agent.", "").replaceAll(".", " ");
}

function eventSummary(event: AgentRuntimeEvent): string {
  return (
    stepValue(event, "summary") ||
    stepValue(event, "message") ||
    stepValue(event, "status") ||
    event.error ||
    ""
  );
}

function eventIcon(event: AgentRuntimeEvent) {
  const rawType = String(event.type);
  const tool = toolName(event);
  if (rawType.includes("failed")) return <XCircle size={13} />;
  if (rawType.includes("completed")) return <CheckCircle2 size={13} />;
  if (tool.includes("search") || tool.includes("schema")) return <Search size={13} />;
  if (tool.includes("sql") || tool.includes("db") || tool.includes("database")) return <Database size={13} />;
  if (tool.includes("policy") || tool.includes("safety")) return <ShieldCheck size={13} />;
  if (event.type === "agent.artifact.created") return <MessageSquare size={13} />;
  if (rawType.includes("step") || rawType.includes("tool")) return <Wrench size={13} />;
  return <Circle size={13} />;
}
