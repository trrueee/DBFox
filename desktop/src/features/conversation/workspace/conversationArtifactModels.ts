import type {
  ChartArtifact,
  MarkdownArtifact,
  ResultViewArtifact,
  SqlArtifact,
} from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";

export function conversationSqlText(artifact: ConversationArtifact): string {
  const value = artifact.payload.sql || artifact.payload.proposed_sql || artifact.payload.safeSql || artifact.payload.safe_sql;
  return typeof value === "string" ? value : "";
}

export function conversationDependsOn(artifact: ConversationArtifact): string[] {
  const raw = artifact.depends_on as unknown;
  if (Array.isArray(raw)) return raw.filter((item): item is string => typeof item === "string");
  if (raw && typeof raw === "object" && "depends_on" in raw) {
    const nested = (raw as { depends_on?: unknown }).depends_on;
    return Array.isArray(nested) ? nested.filter((item): item is string => typeof item === "string") : [];
  }
  return [];
}

export function isSqlConversationArtifact(artifact: ConversationArtifact): boolean {
  return artifact.type === "sql" || artifact.type === "sql_suggestion";
}

export function isResultViewConversationArtifact(artifact: ConversationArtifact): boolean {
  return artifact.type === "result_view";
}

export function isSqlBackedResultViewArtifact(artifact: ConversationArtifact): boolean {
  if (!isResultViewConversationArtifact(artifact)) return false;
  const storageMode = payloadString(artifact.payload, ["storageMode", "storage_mode"]);
  const safeSql = payloadString(artifact.payload, ["safeSql", "safe_sql", "sourceSql", "source_sql"]);
  return storageMode === "sql_backed" && Boolean(safeSql);
}

export function conversationArtifactKeys(artifact: ConversationArtifact): string[] {
  return [artifact.id, artifact.semantic_id].filter((item): item is string => Boolean(item));
}

export function dependsOnAnyConversationArtifact(artifact: ConversationArtifact, keys: Set<string>): boolean {
  return conversationDependsOn(artifact).some((id) => keys.has(id));
}

export function sortConversationArtifacts(artifacts: ConversationArtifact[]): ConversationArtifact[] {
  return [...artifacts].sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
}

export function conversationTableRows(artifact: ConversationArtifact): unknown[] {
  const rows = artifact.payload.rows || artifact.payload.data || artifact.payload.previewRows;
  return Array.isArray(rows) ? rows : [];
}

export function conversationTableColumns(artifact: ConversationArtifact): string[] {
  const columns = artifact.payload.columns;
  if (Array.isArray(columns)) {
    const names = columns.flatMap((item) => {
      if (typeof item === "string" && item.trim()) return [item];
      if (!item || typeof item !== "object" || Array.isArray(item)) return [];
      const record = item as Record<string, unknown>;
      const name = record.name || record.field || record.column;
      return typeof name === "string" && name.trim() ? [name] : [];
    });
    if (names.length > 0) return names;
  }
  const first = conversationTableRows(artifact)[0];
  return first && typeof first === "object" && !Array.isArray(first) ? Object.keys(first) : [];
}

export function conversationCellText(row: unknown, column: string, index: number): string {
  const value = Array.isArray(row)
    ? row[index]
    : row && typeof row === "object"
      ? (row as Record<string, unknown>)[column]
      : "";
  if (value == null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function payloadNumber(payload: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return undefined;
}

export function payloadString(payload: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

export function payloadStringList(payload: Record<string, unknown>, keys: string[]): string[] | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) {
      const items = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
      if (items.length > 0) return items;
    }
  }
  return undefined;
}

export function payloadBoolean(payload: Record<string, unknown>, keys: string[]): boolean {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "boolean") return value;
  }
  return false;
}

function payloadOptionalBoolean(payload: Record<string, unknown>, keys: string[]): boolean | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "boolean") return value;
  }
  return undefined;
}

function payloadRecordList(payload: Record<string, unknown>, keys: string[]): Array<Record<string, string>> | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (!Array.isArray(value)) continue;
    const records = value.flatMap((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return [];
      const record: Record<string, string> = {};
      for (const [recordKey, recordValue] of Object.entries(item as Record<string, unknown>)) {
        if (typeof recordValue === "string" && recordValue.trim()) record[recordKey] = recordValue;
      }
      return Object.keys(record).length > 0 ? [record] : [];
    });
    if (records.length > 0) return records;
  }
  return undefined;
}

export function safetyGuardrailResult(payload: Record<string, unknown>): string {
  const flattened = payloadString(payload, ["guardrail_result", "guardrailResult"]);
  if (flattened) return flattened;
  const guardrail = payload.guardrail;
  if (guardrail && typeof guardrail === "object") {
    return payloadString(guardrail as Record<string, unknown>, ["result"]) || "unknown";
  }
  return "unknown";
}

export function safetySchemaWarningsCount(payload: Record<string, unknown>): number {
  const count = payloadNumber(payload, ["schema_warnings_count", "schemaWarningsCount"]);
  if (count !== undefined) return count;
  if (Array.isArray(payload.schema_warnings)) return payload.schema_warnings.length;
  if (Array.isArray(payload.schemaWarnings)) return payload.schemaWarnings.length;
  return 0;
}

export function safetyRedactionSummary(payload: Record<string, unknown>): { count: number; fields: string[] } {
  const candidates = [
    payload.redaction,
    payload.redaction_audit,
    payload.redactionAudit,
    payload.audit,
    payload.execution_safety_decision,
    payload.executionSafetyDecision,
  ];

  let count = payloadNumber(payload, ["redacted_count", "redactedCount", "redaction_count", "redactionCount"]) ?? 0;
  const fields = new Set(payloadStringList(payload, ["redacted_fields", "redactedFields", "fields", "sensitive_fields", "sensitiveFields"]) || []);

  for (const item of candidates) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    count = Math.max(
      count,
      payloadNumber(record, ["redacted_count", "redactedCount", "count", "field_count", "fieldCount"]) ?? 0,
    );
    for (const field of payloadStringList(record, ["fields", "redacted_fields", "redactedFields", "sensitive_fields", "sensitiveFields"]) || []) {
      fields.add(field);
    }
  }

  return { count: Math.max(count, fields.size), fields: Array.from(fields).slice(0, 8) };
}

export function toResultViewArtifactModel(artifact: ConversationArtifact): ResultViewArtifact {
  const columns = conversationTableColumns(artifact);
  const rows = conversationTableRows(artifact).map((row) =>
    columns.map((column, index) => conversationCellText(row, column, index)),
  );
  const rowCount = payloadNumber(artifact.payload, ["rowCount", "row_count"]) ?? rows.length;
  const returnedRows = payloadNumber(artifact.payload, ["returnedRows", "returned_rows"]) ?? rows.length;

  return {
    id: artifact.id,
    type: "result_view",
    title: artifact.title,
    storageMode: payloadString(artifact.payload, ["storageMode", "storage_mode"]) === "sql_backed" ? "sql_backed" : "payload",
    datasourceId: payloadString(artifact.payload, ["datasourceId", "datasource_id"]) || "",
    sourceSqlSemanticId: payloadString(artifact.payload, [
      "sourceSqlArtifactId",
      "source_sql_artifact_id",
      "sourceSqlSemanticId",
      "source_sql_semantic_id",
    ]) || "",
    sourceSql: payloadString(artifact.payload, ["sourceSql", "source_sql"]) || "",
    safeSql: payloadString(artifact.payload, ["safeSql", "safe_sql"]) || "",
    columns,
    previewRows: payloadString(artifact.payload, ["storageMode", "storage_mode"]) === "sql_backed" ? rows : rows.slice(0, 10),
    previewRowCount: payloadNumber(artifact.payload, ["previewRowCount", "preview_row_count"]) || Math.min(rows.length, 10),
    rows,
    rowCount,
    returnedRows,
    latencyMs: payloadNumber(artifact.payload, ["latencyMs", "latency_ms"]),
    truncated: Boolean(artifact.payload.truncated),
    warnings: payloadStringList(artifact.payload, ["warnings"]),
    notices: payloadStringList(artifact.payload, ["notices"]),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

export function toSqlArtifactModel(artifact: ConversationArtifact): SqlArtifact {
  return {
    id: artifact.id,
    type: "sql",
    title: artifact.title,
    description: payloadString(artifact.payload, ["purpose", "description"]),
    sql: conversationSqlText(artifact),
    purpose: payloadString(artifact.payload, ["purpose"]),
    usedTables: payloadStringList(artifact.payload, ["usedTables", "used_tables", "tables"]),
    validationStatus: payloadString(artifact.payload, ["validationStatus", "validation_status"]),
    executionStatus: payloadString(artifact.payload, ["executionStatus", "execution_status"]),
    rowCount: payloadNumber(artifact.payload, ["rowCount", "row_count"]),
    latencyMs: payloadNumber(artifact.payload, ["latencyMs", "latency_ms"]),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

export function toMarkdownArtifactModel(artifact: ConversationArtifact): MarkdownArtifact {
  return {
    id: artifact.id,
    type: "markdown",
    title: artifact.title,
    content: payloadString(artifact.payload, ["content", "markdown", "message", "error"]) || artifact.title,
    description: payloadString(artifact.payload, ["description"]),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}

function chartSeries(artifact: ConversationArtifact): ChartArtifact["series"] {
  const series = artifact.payload.series;
  if (!Array.isArray(series)) return [];
  return series.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const label = record.label ?? record.name ?? record.x;
    const value = Number(record.value ?? record.y);
    if (typeof label !== "string" || !Number.isFinite(value)) return [];
    const rawX = record.x;
    const x = typeof rawX === "string" || typeof rawX === "number" ? rawX : undefined;
    return [{ label, value, x }];
  });
}

function chartType(artifact: ConversationArtifact): ChartArtifact["chartType"] {
  const value = artifact.payload.type || artifact.payload.chart_type || artifact.payload.kind;
  if (value === "line" || value === "pie" || value === "scatter" || value === "area") return value;
  return "bar";
}

function chartSourceRefs(payload: Record<string, unknown>): ChartArtifact["sourceRefs"] {
  const raw = payload.source_refs;
  if (!Array.isArray(raw)) return undefined;
  const refs = raw.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const label = typeof record.label === "string" ? record.label : "";
    const formula = typeof record.formula === "string" ? record.formula : "";
    const field = typeof record.field === "string" ? record.field : "";
    return label && formula && field ? [{ label, formula, field }] : [];
  });
  return refs.length > 0 ? refs : undefined;
}

export function toChartArtifactModel(artifact: ConversationArtifact): ChartArtifact {
  return {
    id: artifact.id,
    type: "chart",
    title: artifact.title,
    description: payloadString(artifact.payload, ["reason", "description"]),
    chartType: chartType(artifact),
    unit: payloadString(artifact.payload, ["unit"]),
    xLabel: payloadString(artifact.payload, ["xLabel", "x_label", "x"]),
    yLabel: payloadString(artifact.payload, ["yLabel", "y_label", "y"]),
    seriesLabel: payloadString(artifact.payload, ["seriesLabel", "series_label", "yLabel", "y_label", "y"]),
    dataLabel: payloadOptionalBoolean(artifact.payload, ["dataLabel", "data_label"]),
    sampleSize: payloadNumber(artifact.payload, ["sampleSize", "sample_size"]),
    dimensions: payloadRecordList(artifact.payload, ["dimensions"]),
    metrics: payloadRecordList(artifact.payload, ["metrics"]),
    series: chartSeries(artifact),
    sourceRefs: chartSourceRefs(artifact.payload),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
}
