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
    if (isSqlBackedResultViewArtifact(artifact)) {
      const rowCount = numberValue((artifact.payload as Record<string, unknown>).rowCount);
      add({ type: "result", artifactId: artifact.id, rowCount, label: artifact.title || "结果表" });
    }
    if (artifact.type === "chart") {
      add({ type: "chart", artifactId: artifact.id, label: artifact.title || "图表" });
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
  if (reference.type === "result" && reference.rowCount !== undefined) return `${reference.rowCount} 行结果`;
  return reference.label;
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return undefined;
}
