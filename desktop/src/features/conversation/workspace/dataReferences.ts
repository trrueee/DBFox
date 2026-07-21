import type { DataReference } from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";
import { isSqlBackedResultViewArtifact } from "./conversationArtifactModels";

export function buildDataReferences(artifacts: ConversationArtifact[]): DataReference[] {
  const references: DataReference[] = [];
  const seen = new Set<string>();
  const add = (reference: DataReference) => {
    const key = referenceKey(reference);
    if (!seen.has(key)) { seen.add(key); references.push(reference); }
  };
  for (const artifact of artifacts) {
    if (artifact.type === "sql" || artifact.type === "sql_suggestion") {
      const sql = sqlText(artifact);
      for (const table of tableNames(artifact.payload.usedTables)) add({ type: "table", table, label: table });
      add({ type: "sql", artifactId: artifact.id, label: `SQL: ${artifact.title}`, sql });
    }
    if (isSqlBackedResultViewArtifact(artifact)) {
      const rowCount = numberValue(artifact.payload.rowCount);
      add({ type: "result", artifactId: artifact.id, rowCount, label: artifact.title || "结果表" });
    }
    if (artifact.type === "chart") {
      add({ type: "chart", artifactId: artifact.id, label: artifact.title || "图表" });
      const sourceRefs = Array.isArray(artifact.payload.sourceRefs) ? artifact.payload.sourceRefs : [];
      for (const sourceRef of sourceRefs) {
        if (!sourceRef || typeof sourceRef !== "object") continue;
        const field = typeof (sourceRef as Record<string, unknown>).field === "string"
          ? String((sourceRef as Record<string, unknown>).field) : "";
        if (!field) continue;
        const [table, column] = splitField(field);
        add({ type: "column", table, column, label: field });
      }
    }
  }
  return references;
}

export function referenceKey(reference: DataReference): string {
  if (reference.type === "table") return `table:${reference.schema || ""}.${reference.table}`;
  if (reference.type === "column") return `column:${reference.table || ""}.${reference.column}`;
  return `${reference.type}:${reference.artifactId}`;
}

export function referenceTitle(reference: DataReference): string {
  if (reference.type === "sql") return "打开 SQL 工作台";
  if (reference.type === "result" && reference.rowCount !== undefined) return `${reference.rowCount} 行结果`;
  return reference.label;
}

function sqlText(artifact: ConversationArtifact): string {
  const value = artifact.payload.sql || artifact.payload.safeSql;
  return typeof value === "string" ? value : "";
}
function tableNames(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : [];
}
function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return undefined;
}
function splitField(field: string): [string | undefined, string] {
  const parts = field.split(".");
  return parts.length < 2 ? [undefined, field] : [parts.slice(0, -1).join("."), parts.at(-1)!];
}
