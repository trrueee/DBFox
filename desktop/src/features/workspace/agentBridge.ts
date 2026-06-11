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
  MetricArtifact,
  SqlArtifact,
  TableArtifact,
  TraceArtifact,
} from "../../types/agentArtifact";

// ---------------------------------------------------------------------------
// Backend AgentArtifact (payload-based) → hifi view artifact models
// ---------------------------------------------------------------------------

const TYPE_ORDER: Record<string, number> = {
  metric: 0,
  chart: 1,
  table: 2,
  sql: 3,
  trace: 4,
  markdown: 5,
  sql_suggestion: 6,
  insight: 7,
  recommendation: 8,
  error: 9,
};

/** Artifact types that stay internal — raw agent plans are too noisy for users. */
const HIDDEN_TYPES = new Set(["agent_plan"]);

export function toViewArtifacts(artifacts: ApiAgentArtifact[]): ViewAgentArtifact[] {
  const visible = artifacts.filter(
    (artifact) => !HIDDEN_TYPES.has(artifact.type) && artifact.presentation?.mode !== "hidden",
  );

  const result: ViewAgentArtifact[] = [];
  const derivedSummary = buildDerivedMetricArtifact(artifacts);
  if (derivedSummary) result.push(derivedSummary);

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
    case "query_plan":
      return mapQueryPlanTraceArtifact(artifact);
    case "safety":
      return mapSafetyTraceArtifact(artifact);
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

  const rows: string[][] = rawRows.map((row) => {
    if (Array.isArray(row)) return columns.map((_, index) => formatCell(row[index]));
    if (row && typeof row === "object") {
      const record = row as Record<string, unknown>;
      return columns.map((column) => formatCell(record[column]));
    }
    return columns.map(() => "");
  });

  const rowCount = readNumber(payload, ["rowCount", "row_count", "total", "total_rows"]) ?? rows.length;
  return {
    id: artifact.id,
    type: "table",
    title: artifact.title || "查询结果",
    description: `${rowCount} 行 · ${columns.length} 列`,
    columns,
    rows,
  };
}

function mapChartArtifact(artifact: ApiAgentArtifact, all: ApiAgentArtifact[]): ChartArtifact | null {
  const payload = artifact.payload || {};
  const chartType = normalizeChartType(firstString(payload, ["type", "chartType", "chart_type"]));
  const x = firstString(payload, ["x", "x_field", "dimension", "label"]);
  const y = firstString(payload, ["y", "y_field", "metric", "value"]);

  const directSeries = readSeries(payload.series);
  if (directSeries.length > 0) {
    return {
      id: artifact.id,
      type: "chart",
      title: artifact.title || "数据图表",
      description: typeof payload.reason === "string" ? payload.reason : undefined,
      chartType,
      unit: typeof payload.unit === "string" ? payload.unit : undefined,
      series: directSeries,
    };
  }

  if (!x || !y) return null;

  // The chart artifact is often only a suggestion {type, x, y}; series data lives
  // in the companion result table artifact.
  const tableArtifact = all.find((item) => item.type === "table");
  const rowsValue = tableArtifact?.payload?.rows;
  const rawRows = Array.isArray(rowsValue) ? rowsValue : [];
  const series: Array<{ label: string; value: number }> = [];
  for (const row of rawRows) {
    if (!row || typeof row !== "object" || Array.isArray(row)) continue;
    const record = row as Record<string, unknown>;
    const value = Number(record[y]);
    if (!Number.isFinite(value)) continue;
    series.push({ label: formatCell(record[x]), value });
    if (series.length >= 120) break;
  }
  if (series.length === 0) return null;

  return {
    id: artifact.id,
    type: "chart",
    title: artifact.title || `${y} 按 ${x} 分布`,
    description: typeof payload.reason === "string" ? payload.reason : undefined,
    chartType,
    unit: typeof payload.unit === "string" ? payload.unit : undefined,
    series,
  };
}

function normalizeChartType(value: string): ChartArtifact["chartType"] {
  const normalized = value.toLowerCase();
  if (normalized === "line" || normalized === "bar" || normalized === "scatter" || normalized === "pie" || normalized === "area") {
    return normalized;
  }
  return "bar";
}

function readSeries(value: unknown): Array<{ label: string; value: number }> {
  if (!Array.isArray(value)) return [];
  const series: Array<{ label: string; value: number }> = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const label = firstString(record, ["label", "name", "x", "dimension"]);
    const rawValue = record.value ?? record.y ?? record.metric;
    const numericValue = Number(rawValue);
    if (!label || !Number.isFinite(numericValue)) continue;
    series.push({ label, value: numericValue });
    if (series.length >= 120) break;
  }
  return series;
}

function mapQueryPlanTraceArtifact(artifact: ApiAgentArtifact): TraceArtifact | null {
  const payload = unwrapPayload(artifact.payload || {}, ["query_plan", "plan", "raw_plan"]);
  const goal = firstString(payload, ["analysis_goal", "intent", "goal", "question"]);
  const tables = asStringList(payload.candidate_tables || payload.tables || payload.selected_tables || payload.table_names);
  const metrics = describeObjectList(payload.metrics, ["name", "label", "expression"]);
  const dimensions = describeObjectList(payload.dimensions, ["name", "label", "column"]);
  const filters = describeObjectList(payload.filters, ["column", "field", "operator", "value"]);
  const assumptions = asStringList(payload.assumptions);
  const warnings = asStringList(payload.warnings || payload.risk_notes);

  const stages: TraceArtifact["stages"] = [
    {
      label: "需求理解",
      status: goal ? "success" : "warning",
      detail: goal || "没有拿到明确的分析目标，复杂问题可能需要补充业务口径。",
    },
    {
      label: "Schema / 表选择",
      status: tables.length ? "success" : "warning",
      detail: tables.length ? tables.join("、") : "未明确候选表，可能导致 SQL 生成不稳定。",
    },
    {
      label: "指标与维度拆解",
      status: metrics.length || dimensions.length ? "success" : "warning",
      detail: [metrics.length ? `指标：${metrics.join("；")}` : "未明确指标", dimensions.length ? `维度：${dimensions.join("；")}` : "未明确维度"].join("\n"),
    },
  ];

  if (filters.length) {
    stages.push({ label: "过滤条件", status: "success", detail: filters.join("；") });
  }
  if (assumptions.length) {
    stages.push({ label: "口径假设", status: "warning", detail: assumptions.join("\n") });
  }
  if (warnings.length) {
    stages.push({ label: "风险提示", status: "warning", detail: warnings.join("\n") });
  }

  return {
    id: artifact.id,
    type: "trace",
    title: artifact.title || "分析链路",
    description: "把复杂问数拆成可复查的任务链路，便于定位表选择、口径、过滤条件是否跑偏。",
    stages,
  };
}

function mapSafetyTraceArtifact(artifact: ApiAgentArtifact): TraceArtifact | null {
  const payload = artifact.payload || {};
  const risk = firstString(payload, ["riskLevel", "risk_level", "result", "status"]);
  const checks = Array.isArray(payload.checks) ? payload.checks : [];
  const messages = asStringList(payload.messages || payload.schemaWarnings || payload.schema_warnings);
  const stages: TraceArtifact["stages"] = [];

  stages.push({
    label: "SQL 安全策略",
    status: risk === "danger" || risk === "reject" ? "failed" : risk === "warning" || risk === "warn" ? "warning" : "success",
    detail: risk ? `风险级别：${risk}` : "已执行基础安全校验。",
  });

  for (const check of checks.slice(0, 6)) {
    if (!check || typeof check !== "object") continue;
    const record = check as Record<string, unknown>;
    const level = String(record.level || record.result || "success");
    stages.push({
      label: String(record.rule || record.name || "策略检查"),
      status: level === "reject" || level === "danger" ? "failed" : level === "warn" || level === "warning" ? "warning" : "success",
      detail: firstString(record, ["message", "reason", "detail"]),
    });
  }

  if (messages.length) {
    stages.push({ label: "补充信息", status: "warning", detail: messages.join("\n") });
  }

  return {
    id: artifact.id,
    type: "trace",
    title: artifact.title || "安全与稳定性检查",
    description: "展示 SQL 执行前的策略判断，避免复杂任务静默失败或误执行危险语句。",
    stages,
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
    title: artifact.title || "数据洞察",
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
    title: artifact.title || "建议的下一步",
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

function buildDerivedMetricArtifact(artifacts: ApiAgentArtifact[]): MetricArtifact | null {
  const tableArtifact = artifacts.find((item) => item.type === "table");
  const tablePayload = tableArtifact?.payload || {};
  const rowsValue = tablePayload.rows;
  const rawRows = Array.isArray(rowsValue) ? rowsValue : [];
  const rowCount = readNumber(tablePayload, ["rowCount", "row_count", "total", "total_rows"]) ?? rawRows.length;
  const columns = Array.isArray(tablePayload.columns) ? tablePayload.columns : [];
  const hasSql = artifacts.some((item) => item.type === "sql" || item.type === "sql_suggestion");
  const hasChart = artifacts.some((item) => item.type === "chart");
  const hasInsight = artifacts.some((item) => item.type === "insight" || item.type === "recommendation");
  const safetyArtifact = artifacts.find((item) => item.type === "safety");
  const risk = safetyArtifact ? firstString(safetyArtifact.payload || {}, ["riskLevel", "risk_level", "result", "status"]) : "";

  const cards: MetricArtifact["cards"] = [];
  if (tableArtifact) {
    cards.push({ label: "结果规模", value: `${rowCount} 行`, helper: `${columns.length} 列，来自真实查询结果`, tone: "good" });
  }
  cards.push({ label: "SQL 证据", value: hasSql ? "已生成" : "缺失", helper: hasSql ? "可打开到 SQL 控制台复查" : "没有可复查 SQL，回答可信度会下降", tone: hasSql ? "good" : "warn" });
  cards.push({ label: "可视化", value: hasChart ? "已建议" : "未生成", helper: hasChart ? "已根据结果字段生成图表建议" : "复杂分析建议补充图表建议", tone: hasChart ? "good" : "warn" });
  cards.push({ label: "结论层", value: hasInsight ? "已产出" : "待增强", helper: hasInsight ? "包含洞察或下一步建议" : "仅有原始结果，缺少业务解读", tone: hasInsight ? "good" : "warn" });
  if (risk) {
    cards.push({
      label: "安全等级",
      value: risk,
      helper: "来自 SQL 策略 / TrustGate / Guardrail 检查",
      tone: risk === "danger" || risk === "reject" ? "danger" : risk === "warning" || risk === "warn" ? "warn" : "good",
    });
  }

  if (!tableArtifact && !hasSql && !hasChart && !hasInsight && !risk) return null;
  return {
    id: "derived-analysis-summary",
    type: "metric",
    title: "分析交付概览",
    description: "用指标卡快速判断这次 Agent 交付是否包含 SQL、结果、图表、结论和安全检查。",
    cards,
  };
}

function unwrapPayload(payload: Record<string, unknown>, keys: string[]): Record<string, unknown> {
  for (const key of keys) {
    const value = payload[key];
    if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  }
  return payload;
}

function firstString(payload: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" || typeof value === "boolean") return String(value);
  }
  return "";
}

function readNumber(payload: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return null;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (typeof item === "number" || typeof item === "boolean") return String(item);
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        return firstString(record, ["name", "label", "title", "column", "table", "expression", "value"]);
      }
      return "";
    })
    .filter(Boolean);
}

function describeObjectList(value: unknown, preferredKeys: string[]): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (!item || typeof item !== "object") return "";
      const record = item as Record<string, unknown>;
      const parts = preferredKeys.map((key) => firstString(record, [key])).filter(Boolean);
      return parts.length ? parts.join(" / ") : JSON.stringify(record);
    })
    .filter(Boolean);
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

export function describeRuntimeEvent(event: AgentRuntimeEvent): string | null {
  if (event.type === "agent.run.started") return "思考中…";
  if (event.type === "agent.step.started") return "思考中…";
  if (event.type === "agent.context.update") {
    const summary = event.step?.summary;
    if (typeof summary === "string" && summary.trim()) return summary.trim();
  }
  if (event.type === "agent.step.completed") {
    const summary = event.step?.summary;
    if (typeof summary === "string" && summary.trim()) return summary.trim();
    const name = event.step?.name;
    if (typeof name === "string" && name.trim()) return `正在处理：${name}`;
  }
  if (event.type === "agent.run.failed" && event.error) return `执行失败：${event.error}`;
  return null;
}

export function buildAnswerText(answer: AgentAnswer | null | undefined, fallback?: string | null): string {
  if (!answer || !answer.answer) {
    return fallback?.trim() || "已为您生成分析结果。";
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
