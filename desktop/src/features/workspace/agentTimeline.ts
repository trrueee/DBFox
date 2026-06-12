import type { AgentRuntimeEvent, AgentRunResponse, AgentStep } from "../../lib/api/types";

export type AgentTimelineItemKind = "user" | "assistant" | "tool";
export type AgentTimelineStatus = "running" | "success" | "failed" | "skipped" | "info";

export interface AgentTimelineItem {
  id: string;
  kind: AgentTimelineItemKind;
  title: string;
  subtitle?: string;
  content?: string;
  status: AgentTimelineStatus;
  toolName?: string;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: string | null;
  latencyMs?: number | null;
}

export function createInitialAgentTimeline(question: string): AgentTimelineItem[] {
  return [{
    id: "user-request",
    kind: "user",
    title: "User",
    content: question,
    status: "info",
  }];
}

export function appendAgentRuntimeEvent(
  current: AgentTimelineItem[],
  event: AgentRuntimeEvent,
): AgentTimelineItem[] {
  if (event.type === "agent.run.started") {
    return upsertById(current, {
      id: "agent-started",
      kind: "assistant",
      title: "AI",
      content: "开始分析请求，准备选择工具。",
      status: "running",
    });
  }

  if (event.type === "agent.progress.update" && event.step) {
    return appendAssistantProgress(current, event);
  }

  if ((event.type === "agent.step.started" || event.type === "agent.step.completed") && event.step) {
    return upsertToolStep(current, event);
  }

  if (event.type === "agent.answer.completed" && event.answer?.answer) {
    return upsertById(current, {
      id: "agent-answer",
      kind: "assistant",
      title: "AI",
      content: event.answer.answer,
      status: "success",
    });
  }

  if (event.type === "agent.run.failed") {
    return upsertById(current, {
      id: "agent-failed",
      kind: "assistant",
      title: "Agent stopped",
      content: event.error || event.response?.error || "Agent run failed.",
      status: "failed",
    });
  }

  return current;
}

export function timelineFromFinalResponse(
  current: AgentTimelineItem[],
  response: AgentRunResponse,
): AgentTimelineItem[] {
  let next = [...current];
  for (const step of response.steps || []) {
    next = upsertById(next, itemFromStep(step, next));
  }
  if (response.answer?.answer) {
    next = upsertById(next, {
      id: "agent-answer",
      kind: "assistant",
      title: "AI",
      content: response.answer.answer,
      status: response.success || response.status === "completed" || response.status === "success" ? "success" : "info",
    });
  }
  if (!response.success && response.error && !response.answer?.answer) {
    next = upsertById(next, {
      id: "agent-failed",
      kind: "assistant",
      title: "Agent stopped",
      content: response.error,
      status: "failed",
    });
  }
  return next;
}

function appendAssistantProgress(current: AgentTimelineItem[], event: AgentRuntimeEvent): AgentTimelineItem[] {
  const summary = normalizeAgentProgressText(stringValue(event.step?.summary) || stringValue(event.step?.detail));
  if (!summary) return current;
  const previous = findLatestAssistantProgress(current);
  if (previous?.content === summary) return current;
  return upsertById(current, {
    id: `progress-${event.sequence}`,
    kind: "assistant",
    title: "AI",
    content: summary,
    status: statusValue(event.step?.status, "info"),
  });
}

function upsertToolStep(current: AgentTimelineItem[], event: AgentRuntimeEvent): AgentTimelineItem[] {
  const step = event.step || {};
  const toolName = stringValue(step.tool_name) || stringValue(step.name) || "tool";
  const id = `tool-${toolName}`;
  const previous = current.find((item) => item.id === id);
  const input = recordValue(step.input) ?? previous?.input ?? null;
  const output = recordValue(step.output) ?? previous?.output ?? null;
  const error = stringValue(step.error) || previous?.error || null;
  const content = event.type === "agent.step.completed"
    ? toolStepSummary(toolName, output, error)
    : previous?.content;

  return upsertById(current, {
    id,
    kind: "tool",
    title: toolName,
    subtitle: stringValue(step.name),
    status: event.type === "agent.step.started" ? "running" : statusValue(step.status, "success"),
    toolName,
    content,
    input,
    output,
    error,
    latencyMs: numberValue(step.latency_ms) ?? previous?.latencyMs ?? null,
  });
}

function itemFromStep(step: AgentStep, current: AgentTimelineItem[]): AgentTimelineItem {
  const existing = current.find((item) => item.kind === "tool" && (item.subtitle === step.name || item.title === step.name));
  return {
    id: existing?.id || `tool-${step.name}`,
    kind: "tool",
    title: existing?.title || step.name,
    subtitle: existing?.subtitle,
    status: step.status,
    toolName: existing?.toolName || step.name,
    input: step.input ?? null,
    output: step.output ?? null,
    error: step.error ?? null,
    latencyMs: step.latency_ms ?? null,
  };
}

function upsertById(items: AgentTimelineItem[], item: AgentTimelineItem): AgentTimelineItem[] {
  const index = items.findIndex((existing) => existing.id === item.id);
  if (index === -1) return [...items, item];
  const next = [...items];
  next[index] = { ...next[index], ...item };
  return next;
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function statusValue(value: unknown, fallback: AgentTimelineStatus): AgentTimelineStatus {
  if (value === "running" || value === "success" || value === "failed" || value === "skipped" || value === "info") {
    return value;
  }
  return fallback;
}

function toolStepSummary(toolName: string, output: Record<string, unknown> | null, error: string | null): string | undefined {
  if (error) return error;
  if (!output) return undefined;

  if (toolName === "db.query" || toolName === "query_database") {
    const rows = numberValue(output.returned_rows) ?? numberValue(output.rowCount) ?? arrayLength(output.rows);
    const cols = arrayLength(output.columns);
    return `返回 ${rows ?? 0} 行${cols !== null ? ` · ${cols} 列` : ""}`;
  }
  if (toolName === "db.preview" || toolName === "preview_table") {
    const table = stringValue(output.table);
    const rows = numberValue(output.returned_rows) ?? arrayLength(output.rows);
    return `${table || "预览数据"}：${rows ?? 0} 行样例`;
  }
  if (toolName === "db.inspect" || toolName === "inspect_database") {
    const table = stringValue(output.name) || stringValue(output.table);
    const cols = arrayLength(output.columns);
    const names = columnNames(output.columns);
    return `${table || "表结构"}：${cols ?? 0} 列${names ? `，${names}` : ""}`;
  }
  if (toolName === "schema.describe_table" || toolName === "describe_table") {
    const table = stringValue(output.table_name);
    const cols = arrayLength(output.columns);
    const names = columnNames(output.columns);
    return `${table || "表结构"}：${cols ?? 0} 列${names ? `，${names}` : ""}`;
  }
  if (toolName === "schema.list_tables" || toolName === "list_tables") {
    const tables = arrayLength(output.tables) ?? numberValue(output.table_count);
    return `发现 ${tables ?? 0} 张表`;
  }
  if (toolName === "schema.refresh_catalog" || toolName === "refresh_catalog") {
    return `目录已刷新：新增 ${numberValue(output.tables_created) ?? 0} 张表，更新 ${numberValue(output.tables_updated) ?? 0} 张表`;
  }
  if (toolName === "db.search" || toolName === "search_database") {
    return `匹配 ${numberValue(output.total_matches) ?? arrayLength(output.results) ?? 0} 个表/字段`;
  }
  if (toolName === "db.observe" || toolName === "observe_database") {
    return `观察到 ${numberValue(output.table_count) ?? 0} 张表`;
  }

  return stringValue(output.message) || "工具执行完成";
}

function arrayLength(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null;
}

function columnNames(value: unknown): string {
  if (!Array.isArray(value)) return "";
  const names = value
    .slice(0, 8)
    .map((item) => {
      if (!item || typeof item !== "object") return "";
      const record = item as Record<string, unknown>;
      return stringValue(record.name) || stringValue(record.column_name);
    })
    .filter(Boolean);
  return names.join(", ");
}

export function normalizeAgentProgressText(text: string): string {
  const normalized = text.trim();
  if (!normalized) return "";

  const exact: Record<string, string> = {
    "Tool observation received; continuing ReAct loop.": "",
    "Model produced a final text response.": "",
    "Answer payload exists.": "",
    "Query failed — revising SQL based on the error.": "查询遇到问题，正在根据错误调整。",
    "Use sql.revise with the execution error, re-validate, then retry.": "正在重新校验查询并准备重试。",
    "Column not found — looking up schema to fix the query.": "字段不匹配，正在核对表结构。",
    "Use schema.describe_table and fuzzy-match similar columns, then sql.revise.": "正在查找相近字段并修正查询。",
  };
  if (Object.prototype.hasOwnProperty.call(exact, normalized)) return exact[normalized];

  if (/^Query failed/i.test(normalized)) return "查询遇到问题，正在修正。";
  if (/^Column not found/i.test(normalized)) return "字段不匹配，正在核对表结构。";
  if (/^\[?[a-z_]+\.[a-z_]+\]/i.test(normalized)) return normalized;
  if (/^[A-Z][A-Za-z\s._-]+(?:\.|:)/.test(normalized)) return "";

  return normalized;
}

function findLatestAssistantProgress(items: AgentTimelineItem[]): AgentTimelineItem | undefined {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item.kind === "assistant" && item.id.startsWith("progress-")) return item;
  }
  return undefined;
}
