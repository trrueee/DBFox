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
  ResultViewArtifact,
  SqlArtifact,
  TableArtifact,
} from "../../types/agentArtifact";
import { normalizeAgentProgressText } from "./agentTimeline";

// ---------------------------------------------------------------------------
// Backend AgentArtifact (payload-based) → hifi view artifact models
// ---------------------------------------------------------------------------

const TYPE_ORDER: Record<string, number> = {
  sql: 0,
  sql_suggestion: 1,
  safety: 2,
  result_view: 3,
  table: 4,
  chart: 5,
  insight: 6,
  recommendation: 7,
  error: 8,
};

/** Artifact types that stay internal — progress is narrated in the chat stream instead. */
const HIDDEN_TYPES = new Set(["agent_plan", "query_plan"]);

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
  switch (artifact.type as string) {
    case "sql":
    case "sql_suggestion":
      return mapSqlArtifact(artifact);
    case "table":
      return mapTableArtifact(artifact);
    case "result_view":
      return mapResultViewArtifact(artifact);
    case "safety":
      return mapSafetyArtifact(artifact);
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
    purpose: firstString(payload, ["purpose"]),
    usedTables: stringArray(payload.used_tables),
    validationStatus: firstString(payload, ["validation_status"]),
    executionStatus: firstString(payload, ["execution_status"]),
    rowCount: numberValue(payload, ["rowCount", "row_count"]),
    latencyMs: numberValue(payload, ["latencyMs", "latency_ms"]),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

function mapTableArtifact(artifact: ApiAgentArtifact): TableArtifact | null {
  const payload = artifact.payload || {};
  const columns = Array.isArray(payload.columns) ? payload.columns.map(String) : [];
  const rawRows = Array.isArray(payload.rows) ? payload.rows : [];
  if (columns.length === 0) return null;

  const rows = rowsFromPayload(columns, rawRows);

  const rowCount = numberValue(payload, ["rowCount", "row_count"]) ?? rows.length;
  const returnedRows = numberValue(payload, ["returnedRows", "returned_rows"]) ?? rows.length;
  const latencyMs = numberValue(payload, ["latencyMs", "latency_ms"]);
  const warnings = stringArray(payload.warnings);
  const notices = stringArray(payload.notices);
  return {
    id: artifact.id,
    type: "table",
    title: "查询结果",
    description: `${rowCount} 行 · ${columns.length} 列`,
    columns,
    rows,
    rowCount,
    returnedRows,
    latencyMs,
    sql: firstString(payload, ["sql"]),
    truncated: Boolean(payload.truncated),
    warnings,
    notices,
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

function mapResultViewArtifact(artifact: ApiAgentArtifact): ResultViewArtifact | null {
  const payload = artifact.payload || {};
  const columns = Array.isArray(payload.columns) ? payload.columns.map(String) : [];
  const rawRows = Array.isArray(payload.previewRows)
    ? payload.previewRows
    : Array.isArray(payload.preview_rows)
      ? payload.preview_rows
      : Array.isArray(payload.rows)
        ? payload.rows
        : [];
  if (columns.length === 0) return null;
  const rows = rowsFromPayload(columns, rawRows);
  const storageMode = firstString(payload, ["storageMode", "storage_mode"]) === "sql_backed" ? "sql_backed" : "payload";
  return {
    id: artifact.id,
    type: "result_view",
    title: artifact.title || "查询结果",
    description: `${numberValue(payload, ["rowCount", "row_count"]) ?? rows.length} 行 · ${columns.length} 列`,
    storageMode,
    datasourceId: firstString(payload, ["datasourceId", "datasource_id"]),
    sourceSqlSemanticId: firstString(payload, ["sourceSqlSemanticId", "source_sql_semantic_id"]),
    sourceSql: firstString(payload, ["sourceSql", "source_sql"]),
    safeSql: firstString(payload, ["safeSql", "safe_sql"]),
    columns,
    previewRows: rows,
    previewRowCount: numberValue(payload, ["previewRowCount", "preview_row_count"]) ?? rows.length,
    rows: storageMode === "payload" ? rows : undefined,
    rowCount: numberValue(payload, ["rowCount", "row_count"]),
    returnedRows: numberValue(payload, ["returnedRows", "returned_rows"]) ?? rows.length,
    latencyMs: numberValue(payload, ["latencyMs", "latency_ms"]),
    truncated: Boolean(payload.truncated),
    warnings: stringArray(payload.warnings),
    notices: stringArray(payload.notices),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

function rowsFromPayload(columns: string[], rawRows: unknown[]): string[][] {
  return rawRows.flatMap((row) => {
    if (Array.isArray(row)) {
      return [columns.map((_, columnIndex) => formatCell(row[columnIndex]))];
    }
    if (row && typeof row === "object") {
      const record = row as Record<string, unknown>;
      return [columns.map((column) => formatCell(record[column]))];
    }
    return [];
  });
}

function mapSafetyArtifact(artifact: ApiAgentArtifact): MarkdownArtifact {
  const payload = artifact.payload || {};
  const canExecute = Boolean(payload.can_execute ?? payload.canExecute);
  const requiresConfirmation = Boolean(payload.requires_confirmation ?? payload.requiresConfirmation);
  const passed = Boolean(payload.passed ?? canExecute);
  const guardrailPayload = payload.guardrail;
  const guardrail = firstString(payload, ["guardrail_result", "guardrailResult"])
    || (guardrailPayload && typeof guardrailPayload === "object"
      ? firstString(guardrailPayload as Record<string, unknown>, ["result"])
      : "")
    || "unknown";
  const schemaWarnings = numberValue(payload, ["schema_warnings_count", "schemaWarningsCount"])
    ?? (Array.isArray(payload.schema_warnings)
      ? payload.schema_warnings.length
      : Array.isArray(payload.schemaWarnings)
        ? payload.schemaWarnings.length
        : 0);
  const lines = [
    passed ? "状态：通过" : "状态：需注意",
    canExecute ? "执行：可执行" : "执行：不可执行",
    requiresConfirmation ? "确认：需要用户确认" : "确认：无需用户确认",
    `Guardrail：${guardrail}`,
    `Schema warnings：${schemaWarnings}`,
  ];
  return {
    id: artifact.id,
    type: "markdown",
    title: "安全检查",
    content: lines.join("\n"),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

function mapChartArtifact(artifact: ApiAgentArtifact, all: ApiAgentArtifact[]): ChartArtifact | null {
  const payload = artifact.payload || {};
  const chartType = firstString(payload, ["chart_type", "chartType", "type", "kind"]).toLowerCase();
  const x = typeof payload.x === "string" ? payload.x : "";
  const y = typeof payload.y === "string" ? payload.y : "";
  const supported = new Set(["line", "bar", "pie", "scatter", "area"]);
  if (!supported.has(chartType) || !x || !y) return null;

  // The backend chart_builder already computes the series from the result set
  // (with aggregation + dedup). Trust it first — reconstructing from the raw
  // table artifact loses aggregation and frequently yields an empty series
  // when the table artifact's row shape differs.
  const series = seriesFromPayload(payload)
    ?? seriesFromTableArtifact(all, x, y);
  if (!series || series.length === 0) return null;

  return {
    id: artifact.id,
    type: "chart",
    title: artifact.title || `${y} 按 ${x} 分布`,
    description: typeof payload.reason === "string" ? payload.reason : undefined,
    chartType: chartType as ChartArtifact["chartType"],
    series,
    sourceRefs: sourceRefsFromPayload(payload),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

/** Use the series already computed by the backend chart_builder. */
function seriesFromPayload(
  payload: Record<string, unknown>,
): ChartArtifact["series"] | null {
  const raw = payload.series;
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const series: ChartArtifact["series"] = [];
  for (const point of raw) {
    if (!point || typeof point !== "object") continue;
    const record = point as Record<string, unknown>;
    const label = formatCell(record.label ?? record.name ?? record.x);
    const value = Number(record.value ?? record.y);
    if (!Number.isFinite(value)) continue;
    const rawX = record.x;
    const x = typeof rawX === "string" || typeof rawX === "number" ? rawX : undefined;
    series.push({ label, value, x });
    if (series.length >= 60) break;
  }
  return series.length > 0 ? series : null;
}

/** Fallback: rebuild series from the raw table artifact rows (pre-aggregation). */
function seriesFromTableArtifact(
  all: ApiAgentArtifact[],
  x: string,
  y: string,
): ChartArtifact["series"] | null {
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
  return series.length > 0 ? series : null;
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

function numberValue(payload: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return undefined;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function sourceRefsFromPayload(
  payload: Record<string, unknown>,
): Array<{ label: string; formula: string; field: string }> {
  const raw = payload.source_refs;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const label = typeof record.label === "string" ? record.label : "";
    const formula = typeof record.formula === "string" ? record.formula : "";
    const field = typeof record.field === "string" ? record.field : "";
    return label && formula && field ? [{ label, formula, field }] : [];
  });
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
  if (event.type === "agent.progress.update") {
    const summary = event.step?.summary ?? event.step?.detail;
    if (typeof summary === "string" && summary.trim()) {
      return normalizeAgentProgressText(summary);
    }
  }
  if (event.type === "agent.context.update") {
    const summary = event.step?.summary;
    if (typeof summary === "string" && summary.trim()) return normalizeContextSummary(summary);
  }
  if (event.type === "agent.step.completed") {
    const summary = event.step?.summary;
    if (typeof summary === "string" && summary.trim()) return summary.trim();
    const name = event.step?.name;
    if (typeof name === "string" && name.trim()) return `正在处理：${name}`;
  }
  return null;
}

function normalizeContextSummary(summary: string): string {
  const text = summary.trim();
  if (/^Using agent SQL/i.test(text) && /\bartifacts?\b/i.test(text)) {
    return "已得到查询结果，正在组织最终回答。";
  }
  if (/^Using agent SQL/i.test(text)) {
    return "正在使用 Agent SQL 分析数据。";
  }
  if (/^Focus:/i.test(text)) {
    return text.replace(/^Focus:/i, "当前重点：").trim();
  }
  return text;
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
