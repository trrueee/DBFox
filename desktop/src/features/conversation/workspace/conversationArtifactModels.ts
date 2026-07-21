import type {
  ChartArtifact,
  MarkdownArtifact,
  ResultViewArtifact,
  SqlArtifact,
} from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";

export function conversationSqlText(artifact: ConversationArtifact): string {
  const value = artifact.payload.sql || artifact.payload.safeSql;
  return typeof value === "string" ? value : "";
}

export function conversationDependsOn(artifact: ConversationArtifact): string[] {
  return (artifact.depends_on || []).filter((item): item is string => typeof item === "string");
}

export function isSqlConversationArtifact(artifact: ConversationArtifact): boolean {
  return artifact.type === "sql" || artifact.type === "sql_suggestion";
}

export function isResultViewConversationArtifact(artifact: ConversationArtifact): boolean {
  return artifact.type === "result_view";
}

export function isSqlBackedResultViewArtifact(artifact: ConversationArtifact): boolean {
  return isResultViewConversationArtifact(artifact);
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
  return [];
}

export function payloadNumber(payload: object, keys: string[]): number | undefined {
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return undefined;
}

export function payloadString(payload: object, keys: string[]): string | undefined {
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

export function payloadStringList(payload: object, keys: string[]): string[] | undefined {
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) {
      const items = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
      if (items.length > 0) return items;
    }
  }
  return undefined;
}

export function payloadBoolean(payload: object, keys: string[]): boolean {
  const record = payload as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") return value;
  }
  return false;
}

export function safetyGuardrailResult(payload: object): string {
  const source = payload as Record<string, unknown>;
  const flattened = payloadString(payload, ["guardrailResult"]);
  if (flattened) return flattened;
  const guardrail = source.guardrail;
  if (guardrail && typeof guardrail === "object") {
    return payloadString(guardrail as Record<string, unknown>, ["result"]) || "unknown";
  }
  return "unknown";
}

export function safetySchemaWarningsCount(payload: object): number {
  const source = payload as Record<string, unknown>;
  const count = payloadNumber(payload, ["schemaWarningsCount"]);
  if (count !== undefined) return count;
  if (Array.isArray(source.schemaWarnings)) return source.schemaWarnings.length;
  return 0;
}

export function safetyRedactionSummary(payload: object): { count: number; fields: string[] } {
  const source = payload as Record<string, unknown>;
  const candidates = [
    source.redaction,
    source.redactionAudit,
    source.audit,
    source.executionSafetyDecision,
  ];

  let count = payloadNumber(payload, ["redactedCount"]) ?? 0;
  const fields = new Set(payloadStringList(payload, ["redactedFields", "fields", "sensitiveFields"]) || []);

  for (const item of candidates) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    count = Math.max(
      count,
      payloadNumber(record, ["redactedCount", "count", "fieldCount"]) ?? 0,
    );
    for (const field of payloadStringList(record, ["fields", "redactedFields", "sensitiveFields"]) || []) {
      fields.add(field);
    }
  }

  return { count: Math.max(count, fields.size), fields: Array.from(fields).slice(0, 8) };
}

export function toResultViewArtifactModel(artifact: ConversationArtifact): ResultViewArtifact {
  const columns = conversationTableColumns(artifact);
  const rowCount = payloadNumber(artifact.payload, ["rowCount"]);
  const returnedRows = payloadNumber(artifact.payload, ["returnedRows"]);
  const sourceSqlArtifactId = payloadString(artifact.payload, ["sourceSqlArtifactId"]) || "";

  return {
    id: artifact.id,
    type: "result_view",
    title: artifact.title,
    sourceSqlArtifactId,
    columns,
    queryFingerprint: payloadString(artifact.payload, ["queryFingerprint"]) || "",
    datasourceGeneration: payloadNumber(artifact.payload, ["datasourceGeneration"]),
    rowCount,
    returnedRows,
    latencyMs: payloadNumber(artifact.payload, ["latencyMs"]),
    truncated: Boolean(artifact.payload.truncated),
    depends_on: artifact.depends_on,
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
    usedTables: payloadStringList(artifact.payload, ["usedTables"]),
    validationStatus: payloadString(artifact.payload, ["validationStatus"]),
    executionStatus: payloadString(artifact.payload, ["executionStatus"]),
    rowCount: payloadNumber(artifact.payload, ["rowCount"]),
    latencyMs: payloadNumber(artifact.payload, ["latencyMs"]),
    depends_on: artifact.depends_on,
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
  };
}

function chartType(artifact: ConversationArtifact): ChartArtifact["chartType"] {
  const value = artifact.payload.chartType;
  if (value === "line" || value === "pie" || value === "scatter" || value === "area") return value;
  return "bar";
}

export function toChartArtifactModel(artifact: ConversationArtifact): ChartArtifact {
  const y = Array.isArray(artifact.payload.y)
    ? artifact.payload.y.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  return {
    id: artifact.id,
    type: "chart",
    title: artifact.title,
    chartType: chartType(artifact),
    sourceResultArtifactId: payloadString(artifact.payload, ["sourceResultArtifactId"]) || "",
    x: payloadString(artifact.payload, ["x"]) || "",
    y,
    aggregation: payloadString(artifact.payload, ["aggregation"]) === "sum" ? "sum" : "none",
    depends_on: artifact.depends_on,
  };
}
