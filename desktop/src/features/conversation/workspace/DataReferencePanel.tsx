import { BarChart2, Braces, Database, FileCode2, Table2 } from "lucide-react";
import type { ConversationArtifact } from "../../../types/conversation";
import type { DataReference } from "../../../types/agentArtifact";

interface DataReferencePanelProps {
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
}

export function DataReferencePanel({ artifacts, onOpenSqlConsole }: DataReferencePanelProps) {
  const references = buildDataReferences(artifacts);
  if (references.length === 0) return null;

  return (
    <div className="conv-data-refs" aria-label="Data references">
      <span className="conv-data-refs-label">数据来源</span>
      <div className="conv-data-ref-list">
        {references.map((reference) => (
          <button
            key={referenceKey(reference)}
            type="button"
            className={`conv-data-ref conv-data-ref-${reference.type}`}
            onClick={() => {
              if (reference.type === "sql") onOpenSqlConsole(reference.sql);
            }}
            title={referenceTitle(reference)}
          >
            {referenceIcon(reference.type)}
            <span>{reference.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function buildDataReferences(artifacts: ConversationArtifact[]): DataReference[] {
  const references: DataReference[] = [];
  const seen = new Set<string>();
  const add = (reference: DataReference) => {
    const key = referenceKey(reference);
    if (seen.has(key)) return;
    seen.add(key);
    references.push(reference);
  };

  for (const artifact of artifacts) {
    if (artifact.type === "sql" || artifact.type === "sql_suggestion") {
      const sql = sqlText(artifact);
      for (const table of tableNames(artifact.payload.used_tables)) {
        add({ type: "table", table, label: table });
      }
      add({ type: "sql", artifactId: artifact.id, label: `SQL: ${artifact.title}`, sql });
    }

    if (artifact.type === "table") {
      const rowCount = numberValue(artifact.payload.rowCount);
      add({ type: "result", artifactId: artifact.id, rowCount, label: artifact.title || "结果表" });
    }

    if (artifact.type === "chart") {
      add({ type: "chart", artifactId: artifact.id, label: artifact.title || "图表" });
      const sourceRefs = Array.isArray(artifact.payload.source_refs) ? artifact.payload.source_refs : [];
      for (const sourceRef of sourceRefs) {
        if (!sourceRef || typeof sourceRef !== "object") continue;
        const record = sourceRef as Record<string, unknown>;
        const field = typeof record.field === "string" ? record.field : "";
        if (!field) continue;
        const [table, column] = splitField(field);
        add({ type: "column", table, column, label: field });
      }
    }
  }
  return references;
}

function sqlText(artifact: ConversationArtifact): string {
  const value = artifact.payload.sql || artifact.payload.proposed_sql || artifact.payload.safe_sql;
  return typeof value === "string" ? value : "";
}

function tableNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return undefined;
}

function splitField(field: string): [string | undefined, string] {
  const parts = field.split(".");
  if (parts.length < 2) return [undefined, field];
  return [parts.slice(0, -1).join("."), parts[parts.length - 1]];
}

function referenceKey(reference: DataReference): string {
  if (reference.type === "table") return `table:${reference.schema || ""}.${reference.table}`;
  if (reference.type === "column") return `column:${reference.table || ""}.${reference.column}`;
  return `${reference.type}:${reference.artifactId}`;
}

function referenceTitle(reference: DataReference): string {
  if (reference.type === "sql") return "打开 SQL 工作台";
  if (reference.type === "result" && reference.rowCount !== undefined) return `${reference.rowCount} 行结果`;
  return reference.label;
}

function referenceIcon(type: DataReference["type"]) {
  if (type === "table") return <Database size={12} />;
  if (type === "column") return <Braces size={12} />;
  if (type === "sql") return <FileCode2 size={12} />;
  if (type === "chart") return <BarChart2 size={12} />;
  return <Table2 size={12} />;
}
