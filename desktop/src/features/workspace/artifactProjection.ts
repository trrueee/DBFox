import type { AgentArtifact as ApiAgentArtifact } from "../../lib/api";
import type {
  AgentArtifact as ViewAgentArtifact,
  ChartArtifact,
  MarkdownArtifact,
  ResultViewArtifact,
  SqlArtifact,
} from "../../types/agentArtifact";

// ---------------------------------------------------------------------------
// Public Agent artifact contract → workspace artifact models
// ---------------------------------------------------------------------------

const TYPE_ORDER: Record<string, number> = {
  sql: 0,
  sql_suggestion: 1,
  safety: 2,
  result_view: 3,
  chart: 4,
  insight: 5,
  recommendation: 6,
  error: 7,
};

/** Artifact types that stay internal — progress is narrated in the chat stream instead. */
const HIDDEN_TYPES = new Set(["agent_plan", "query_plan"]);

export function toViewArtifacts(artifacts: ApiAgentArtifact[]): ViewAgentArtifact[] {
  const visible = artifacts.filter(
    (artifact) => !HIDDEN_TYPES.has(artifact.type) && artifact.presentation?.mode !== "hidden",
  );

  const result: ViewAgentArtifact[] = [];
  for (const artifact of visible) {
    const mapped = mapArtifact(artifact);
    if (mapped) result.push(mapped);
  }
  result.sort((a, b) => (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9));
  return result;
}

function mapArtifact(artifact: ApiAgentArtifact): ViewAgentArtifact | null {
  switch (artifact.type as string) {
    case "sql":
    case "sql_suggestion":
      return mapSqlArtifact(artifact);
    case "result_view":
      return mapResultViewArtifact(artifact);
    case "safety":
      return mapSafetyArtifact(artifact);
    case "chart":
      return mapChartArtifact(artifact);
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
  const sql = firstString(payload, ["sql", "safeSql"]);
  if (!sql) return null;
  return {
    id: artifact.id,
    type: "sql",
    title: artifact.type === "sql_suggestion" ? "SQL 修改建议" : "执行的 SQL",
    description: typeof payload.reason === "string" ? payload.reason : undefined,
    sql,
    purpose: firstString(payload, ["purpose"]),
    usedTables: stringArray(payload.usedTables),
    validationStatus: firstString(payload, ["validationStatus"]),
    executionStatus: firstString(payload, ["executionStatus"]),
    rowCount: numberValue(payload, ["rowCount"]),
    latencyMs: numberValue(payload, ["latencyMs"]),
    depends_on: artifact.depends_on,
  };
}

function mapResultViewArtifact(artifact: ApiAgentArtifact): ResultViewArtifact | null {
  const payload = artifact.payload || {};
  const columns = resultColumnsFromPayload(payload.columns);
  const columnNames = columnNamesFromColumns(columns);
  if (columnNames.length === 0) return null;
  const sourceSqlArtifactId = firstString(payload, ["sourceSqlArtifactId"]);
  return {
    id: artifact.id,
    type: "result_view",
    title: artifact.title || "查询结果",
    description: `${numberValue(payload, ["rowCount"]) ?? 0} 行 · ${columnNames.length} 列`,
    sourceSqlArtifactId,
    columns,
    queryFingerprint: firstString(payload, ["queryFingerprint"]),
    datasourceGeneration: numberValue(payload, ["datasourceGeneration"]),
    rowCount: numberValue(payload, ["rowCount"]),
    returnedRows: numberValue(payload, ["returnedRows"]),
    latencyMs: numberValue(payload, ["latencyMs"]),
    truncated: Boolean(payload.truncated),
    depends_on: artifact.depends_on,
  };
}

function resultColumnsFromPayload(value: unknown): ResultViewArtifact["columns"] {
  if (!Array.isArray(value)) return [];
  const columns: ResultViewArtifact["columns"] = [];
  for (const item of value) {
    if (typeof item === "string" && item.trim()) {
      columns.push(item.trim());
      continue;
    }
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const record = item as Record<string, unknown>;
    const rawName = record.name || record.field || record.column;
    if (typeof rawName !== "string" || !rawName.trim()) continue;
    const rawType = record.type || record.dataType || record.data_type;
    const column: { name: string; type?: string } = { name: rawName.trim() };
    if (typeof rawType === "string" && rawType.trim()) column.type = rawType.trim();
    columns.push(column);
  }
  return columns;
}

function columnNamesFromColumns(columns: ResultViewArtifact["columns"]): string[] {
  return columns.flatMap((column) => {
    if (typeof column === "string" && column.trim()) return [column.trim()];
    if (typeof column === "object" && column.name.trim()) return [column.name.trim()];
    return [];
  });
}

function mapSafetyArtifact(artifact: ApiAgentArtifact): MarkdownArtifact {
  const payload = artifact.payload || {};
  const canExecute = Boolean(payload.canExecute);
  const requiresApproval = Boolean(payload.requiresApproval);
  const passed = Boolean(payload.passed ?? canExecute);
  const guardrailPayload = payload.guardrail;
  const guardrail = firstString(payload, ["guardrailResult"])
    || (guardrailPayload && typeof guardrailPayload === "object"
      ? firstString(guardrailPayload as Record<string, unknown>, ["result"])
      : "")
    || "unknown";
  const schemaWarnings = numberValue(payload, ["schemaWarningsCount"])
    ?? (Array.isArray(payload.schemaWarnings) ? payload.schemaWarnings.length : 0);
  const redaction = redactionSummary(payload);
  const lines = [
    passed ? "状态：通过" : "状态：需注意",
    canExecute ? "执行：可执行" : "执行：不可执行",
    requiresApproval ? "批准：需要用户批准" : "批准：无需用户批准",
    `Guardrail：${guardrail}`,
    `Schema warnings：${schemaWarnings}`,
  ];
  if (redaction.count > 0) {
    lines.push(`脱敏：已脱敏 ${redaction.count} 个字段`);
    if (redaction.fields.length > 0) lines.push(`脱敏字段：${redaction.fields.join(", ")}`);
  }
  return {
    id: artifact.id,
    type: "markdown",
    title: "安全检查",
    content: lines.join("\n"),
    depends_on: artifact.depends_on,
  };
}

function mapChartArtifact(artifact: ApiAgentArtifact): ChartArtifact | null {
  const payload = artifact.payload || {};
  const chartType = firstString(payload, ["chartType"]).toLowerCase();
  const x = typeof payload.x === "string" ? payload.x : "";
  const y = stringArray(payload.y);
  const supported = new Set(["line", "bar", "pie", "scatter", "area"]);
  if (!supported.has(chartType) || !x || y.length === 0) return null;

  const sourceResultArtifactId = firstString(payload, ["sourceResultArtifactId"]);
  if (!sourceResultArtifactId) return null;

  return {
    id: artifact.id,
    type: "chart",
    title: artifact.title || `${y[0]} 按 ${x} 分布`,
    chartType: chartType as ChartArtifact["chartType"],
    sourceResultArtifactId,
    x,
    y,
    aggregation: firstString(payload, ["aggregation"]) === "sum" ? "sum" : "none",
    depends_on: artifact.depends_on,
  };
}

function mapInsightArtifact(artifact: ApiAgentArtifact): MarkdownArtifact | null {
  const payload = artifact.payload || {};
  if (artifact.semantic_id === "semantic_resolution") return null;

  const lines: string[] = [];
  if (typeof payload.rowCount === "number") lines.push(`共 ${payload.rowCount} 行结果。`);
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

function firstString(payload: object, keys: string[]): string {
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function numberValue(payload: object, keys: string[]): number | undefined {
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return undefined;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function stringArrayFromKeys(payload: object, keys: string[]): string[] {
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const items = stringArray(record[key]);
    if (items.length > 0) return items;
  }
  return [];
}

function redactionSummary(payload: object): { count: number; fields: string[] } {
  const recordPayload = payload as Record<string, unknown>;
  const candidates = [
    recordPayload.redaction,
    recordPayload.redactionAudit,
    recordPayload.audit,
    recordPayload.executionSafetyDecision,
  ];
  let count = numberValue(payload, ["redactedCount"]) ?? 0;
  const fields = new Set(stringArrayFromKeys(recordPayload, ["redactedFields", "fields", "sensitiveFields"]));
  for (const item of candidates) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    count = Math.max(
      count,
      numberValue(record, ["redactedCount", "count", "fieldCount"]) ?? 0,
    );
    for (const field of stringArrayFromKeys(record, ["fields", "redactedFields", "sensitiveFields"])) {
      fields.add(field);
    }
  }
  return { count: Math.max(count, fields.size), fields: Array.from(fields).slice(0, 8) };
}
