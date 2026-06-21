import { BarChart2, Copy, Database, Play, Terminal } from "lucide-react";
import type { ConversationArtifact } from "../../../types/conversation";

interface ArtifactEvidencePanelProps {
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
}

function sqlText(artifact: ConversationArtifact): string {
  const value = artifact.payload.sql || artifact.payload.proposed_sql || artifact.payload.safe_sql;
  return typeof value === "string" ? value : "";
}

function groupedArtifacts(artifacts: ConversationArtifact[]) {
  const sql = artifacts
    .filter((item) => item.type === "sql")
    .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  return sql.map((sqlArtifact) => {
    const tables = artifacts.filter(
      (item) => item.type === "table" && item.depends_on.includes(sqlArtifact.id),
    );
    const tableIds = new Set(tables.map((item) => item.id));
    const charts = artifacts.filter(
      (item) =>
        item.type === "chart" &&
        (item.depends_on.includes(sqlArtifact.id) || item.depends_on.some((id) => tableIds.has(id))),
    );
    return { sql: sqlArtifact, tables, charts };
  });
}

export function ArtifactEvidencePanel({ artifacts, onOpenSqlConsole }: ArtifactEvidencePanelProps) {
  const groups = groupedArtifacts(artifacts);
  if (artifacts.length === 0) return null;
  return (
    <details className="conv-evidence" open>
      <summary>
        <Database size={14} />
        <span>{artifacts.length} evidence items</span>
      </summary>
      <div className="conv-evidence-body">
        {groups.map((group, index) => {
          const sql = sqlText(group.sql);
          return (
            <section className="conv-sql-group" key={group.sql.id}>
              <header>
                <span className="conv-sql-title">
                  <Terminal size={13} />
                  {group.sql.title || `SQL ${index + 1}`}
                </span>
                <span className="conv-sql-actions">
                  <button
                    type="button"
                    onClick={() => void navigator.clipboard?.writeText(sql)}
                    title="Copy SQL"
                  >
                    <Copy size={13} />
                  </button>
                  <button type="button" onClick={() => onOpenSqlConsole(sql)} title="Open SQL console">
                    <Play size={13} />
                  </button>
                </span>
              </header>
              <pre>{sql}</pre>
              {group.tables.map((table) => (
                <div className="conv-table-artifact" key={table.id}>
                  <strong>{table.title}</strong>
                </div>
              ))}
              {group.charts.map((chart) => (
                <div className="conv-chart-artifact" key={chart.id}>
                  <BarChart2 size={13} />
                  <strong>{chart.title}</strong>
                </div>
              ))}
            </section>
          );
        })}
      </div>
    </details>
  );
}
