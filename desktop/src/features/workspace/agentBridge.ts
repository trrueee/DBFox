import type {
  AgentAnswer,
  AgentArtifact as ApiAgentArtifact,
  AgentRuntimeEvent,
  FollowUpSuggestion,
} from "../../lib/api";
import type {
  AgentArtifact as ViewAgentArtifact,
  ChartArtifact,
  MarkdownArtifact,
  SqlArtifact,
  TableArtifact,
} from "../../types/agentArtifact";

// ---------------------------------------------------------------------------
// Backend AgentArtifact (payload-based) → hifi view artifact models
// ---------------------------------------------------------------------------

const TYPE_ORDER: Record<string, number> = {
  table: 0,
  chart: 1,
  sql: 2,
  sql_suggestion: 3,
  insight: 4,
  recommendation: 5,
  error: 6,
};

/** Artifact types that stay internal — progress is narrated in the chat stream instead. */
const HIDDEN_TYPES = new Set(["agent_plan", "query_plan", "safety"]);

export function toViewArtifacts(artifacts: ApiAgentArtifact[]): ViewAgentArtifact[] {
  const visible = artifacts.filter(
    (artifact) => !HIDDEN_TYPES.has(artifact.type) && artifact.presentation?.mode !== "hidden",
  );

  const result: ViewAgentArtifact[] = [];
  for (const artifact of visible) {
    const mapped = mapArtifact(artifact, artifacts);
    if (mapped) result.push(mapped);
  }
  result.sort((a, b) => (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9));
  return result;
}

function mapArtifact(artifact: ApiAgentArtifact, all: ApiAgentArtifact[]): ViewAgentArtifact | null {
  switch (artifact.type) {
    case "sql":
    case "sql_suggestion":
      return mapSqlArtifact(artifact);
    case "table":
      return mapTableArtifact(artifact);
    case "chart":
      return mapChartArtifact(artifact, all);
    case "insight":
      return mapInsightArtifact(artifact);
    case "recommendation":
      return mapRecommendationArtifact(artifact);
    case "error":
      return mapErrorArtifact(artifact);
    default:
      return null;
  }
}

function mapSqlArtifact(artifact: ApiAgentArtifact): SqlArtifact | null {
  const payload = artifact.payload || {};
  const sql = firstString(payload, ["sql", "proposed_sql", "safe_sql"]);
  if (!sql) return null;
  return {
    id: artifact.id,
    type: "sql",
    title: artifact.type === "sql_suggestion" ? "SQL 修改建议" : "执行的 SQL",
    description: typeof payload.reason === "string" ? payload.reason : undefined,
    sql,
  };
}

function mapTableArtifact(artifact: ApiAgentArtifact): TableArtifact | null {
  const payload = artifact.payload || {};
  const columns = Array.isArray(payload.columns) ? payload.columns.map(String) : [];
  const rawRows = Array.isArray(payload.rows) ? payload.rows : [];
  if (columns.length === 0) return null;

  const rows: string[][] = rawRows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    .map((row) => columns.map((column) => formatCell(row[column])));

  const rowCount = typeof payload.rowCount === "number" ? payload.rowCount : rows.length;
  return {
    id: artifact.id,
    type: "table",
    title: "查询结果",
    description: `${rowCount} 行 · ${columns.length} 列`,
    columns,
    rows,
  };
}

function mapChartArtifact(artifact: ApiAgentArtifact, all: ApiAgentArtifact[]): ChartArtifact | null {
  const payload = artifact.payload || {};
  const chartType = payload.type;
  const x = typeof payload.x === "string" ? payload.x : "";
  const y = typeof payload.y === "string" ? payload.y : "";
  if ((chartType !== "line" && chartType !== "bar") || !x || !y) return null;

  // The chart artifact is only a suggestion {type, x, y}; series data lives in
  // the companion result_table artifact.
  const tableArtifact = all.find((item) => item.type === "table");
  const rowsValue = tableArtifact?.payload?.rows;
  const rawRows = Array.isArray(rowsValue) ? rowsValue : [];
  const series: Array<{ label: string; value: number }> = [];
  for (const row of rawRows) {
    if (!row || typeof row !== "object") continue;
    const record = row as Record<string, unknown>;
    const value = Number(record[y]);
    if (!Number.isFinite(value)) continue;
    series.push({ label: formatCell(record[x]), value });
    if (series.length >= 60) break;
  }
  if (series.length === 0) return null;

  return {
    id: artifact.id,
    type: "chart",
    title: `${y} 按 ${x} 分布`,
    description: typeof payload.reason === "string" ? payload.reason : undefined,
    chartType,
    series,
  };
}

function mapInsightArtifact(artifact: ApiAgentArtifact): MarkdownArtifact | null {
  const payload = artifact.payload || {};
  if (artifact.semantic_id === "semantic_resolution") return null;

  const lines: string[] = [];
  if (typeof payload.row_count === "number") lines.push(`共 ${payload.row_count} 行结果。`);
  for (const key of ["notable_facts", "detected_patterns", "anomalies", "limitations"] as const) {
    const values = payload[key];
    if (Array.isArray(values)) {
      for (const value of values) {
        if (typeof value === "string" && value.trim()) lines.push(`- ${value.trim()}`);
      }
    }
  }
  if (lines.length === 0) return null;
  return {
    id: artifact.id,
    type: "markdown",
    title: "数据洞察",
    content: lines.join("\n"),
  };
}

function mapRecommendationArtifact(artifact: ApiAgentArtifact): MarkdownArtifact | null {
  const payload = artifact.payload || {};
  const lines: string[] = [];
  if (Array.isArray(payload.recommendations)) {
    for (const item of payload.recommendations) {
      if (typeof item === "string" && item.trim()) lines.push(`- ${item.trim()}`);
    }
  }
  if (Array.isArray(payload.followUpQuestions)) {
    for (const item of payload.followUpQuestions) {
      if (typeof item === "string" && item.trim()) lines.push(`- ${item.trim()}`);
    }
  }
  if (lines.length === 0) return null;
  return {
    id: artifact.id,
    type: "markdown",
    title: "建议的下一步",
    content: lines.join("\n"),
  };
}

function mapErrorArtifact(artifact: ApiAgentArtifact): MarkdownArtifact {
  const payload = artifact.payload || {};
  const message = firstString(payload, ["message", "error", "detail", "reason"]) || JSON.stringify(payload);
  return {
    id: artifact.id,
    type: "markdown",
    title: artifact.title || "执行中遇到的问题",
    content: message,
  };
}

function firstString(payload: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

// ---------------------------------------------------------------------------
// Answer / progress text helpers
// ---------------------------------------------------------------------------

const STEP_LABELS: Record<string, string> = {
  load_follow_up_context: "加载上下文",
  build_schema_context: "分析表结构",
  generate_sql_candidate: "生成 SQL",
  validate_sql: "校验 SQL 安全性",
  execute_sql: "执行查询",
  profile_result: "分析查询结果",
  suggest_chart: "生成图表建议",
  suggest_followups: "整理追问建议",
  answer_synthesizer: "撰写结论",
  approval_interrupt: "等待人工审批",
  plan_agent: "规划任务",
};

export function describeRuntimeEvent(event: AgentRuntimeEvent): string | null {
  if (event.type === "agent.run.started") return "正在理解问题…";
  if (event.type === "agent.step.started") {
    const name = typeof event.step?.name === "string" ? event.step.name : "";
    const label = STEP_LABELS[name] || name;
    return label ? `正在${label}…` : null;
  }
  return null;
}

export function buildAnswerText(answer: AgentAnswer | null | undefined, fallback?: string | null): string {
  if (!answer || !answer.answer) {
    return fallback?.trim() || "分析已完成，结果见下方。";
  }
  const parts: string[] = [answer.answer.trim()];
  if (answer.key_findings?.length) {
    parts.push(answer.key_findings.map((item) => `• ${item}`).join("\n"));
  }
  if (answer.caveats?.length) {
    parts.push(answer.caveats.map((item) => `注意：${item}`).join("\n"));
  }
  return parts.filter(Boolean).join("\n\n");
}

export function buildSuggestionsText(suggestions: FollowUpSuggestion[] | undefined): string | null {
  if (!suggestions?.length) return null;
  const lines = suggestions
    .slice(0, 4)
    .map((item) => `• ${item.question || item.label}`)
    .filter(Boolean);
  if (lines.length === 0) return null;
  return `你可以继续问：\n${lines.join("\n")}`;
}

/** Merge artifacts by semantic identity, keeping the latest version of each. */
export function mergeApiArtifacts(
  current: ApiAgentArtifact[],
  incoming: ApiAgentArtifact[],
): ApiAgentArtifact[] {
  const byKey = new Map<string, ApiAgentArtifact>();
  for (const artifact of [...current, ...incoming]) {
    byKey.set(artifact.semantic_id || artifact.id, artifact);
  }
  return Array.from(byKey.values());
}
