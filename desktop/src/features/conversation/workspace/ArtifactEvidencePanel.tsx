import { BarChart2, Copy, Database, Play, Table2, Terminal } from "lucide-react";
import type { ConversationArtifact } from "../../../types/conversation";

interface ArtifactEvidencePanelProps {
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
}

function sqlText(artifact: ConversationArtifact): string {
  const value = artifact.payload.sql || artifact.payload.proposed_sql || artifact.payload.safe_sql;
  return typeof value === "string" ? value : "";
}

function dependsOn(artifact: ConversationArtifact): string[] {
  const raw = artifact.depends_on as unknown;
  if (Array.isArray(raw)) return raw.filter((item): item is string => typeof item === "string");
  if (raw && typeof raw === "object" && "depends_on" in raw) {
    const nested = (raw as { depends_on?: unknown }).depends_on;
    return Array.isArray(nested) ? nested.filter((item): item is string => typeof item === "string") : [];
  }
  return [];
}

function isSqlArtifact(artifact: ConversationArtifact): boolean {
  return artifact.type === "sql" || artifact.type === "sql_suggestion";
}

function groupedArtifacts(artifacts: ConversationArtifact[]) {
  const sql = artifacts
    .filter(isSqlArtifact)
    .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  return sql.map((sqlArtifact) => {
    const tables = artifacts.filter(
      (item) => item.type === "table" && dependsOn(item).includes(sqlArtifact.id),
    );
    const tableIds = new Set(tables.map((item) => item.id));
    const charts = artifacts.filter(
      (item) =>
        item.type === "chart" &&
        (dependsOn(item).includes(sqlArtifact.id) || dependsOn(item).some((id) => tableIds.has(id))),
    );
    return { sql: sqlArtifact, tables, charts };
  });
}

function tableRows(artifact: ConversationArtifact): unknown[] {
  const rows = artifact.payload.rows || artifact.payload.data;
  return Array.isArray(rows) ? rows : [];
}

function tableColumns(artifact: ConversationArtifact): string[] {
  const columns = artifact.payload.columns;
  if (Array.isArray(columns)) return columns.filter((item): item is string => typeof item === "string");
  const first = tableRows(artifact)[0];
  return first && typeof first === "object" && !Array.isArray(first) ? Object.keys(first) : [];
}

function cellText(row: unknown, column: string, index: number): string {
  const value = Array.isArray(row)
    ? row[index]
    : row && typeof row === "object"
      ? (row as Record<string, unknown>)[column]
      : "";
  if (value == null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function chartSeries(artifact: ConversationArtifact): { label: string; value: number }[] {
  const series = artifact.payload.series;
  if (!Array.isArray(series)) return [];
  return series.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const label = record.label ?? record.name ?? record.x;
    const value = Number(record.value ?? record.y);
    if (typeof label !== "string" || !Number.isFinite(value)) return [];
    return [{ label, value }];
  });
}

export function ArtifactEvidencePanel({ artifacts, onOpenSqlConsole }: ArtifactEvidencePanelProps) {
  const groups = groupedArtifacts(artifacts);
  const groupedIds = new Set(groups.flatMap((group) => [group.sql.id, ...group.tables.map((item) => item.id), ...group.charts.map((item) => item.id)]));
  const orphanArtifacts = artifacts
    .filter((artifact) => !groupedIds.has(artifact.id))
    .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
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
              {group.tables.map((table) => <TableArtifact key={table.id} artifact={table} />)}
              {group.charts.map((chart) => <ChartArtifact key={chart.id} artifact={chart} />)}
            </section>
          );
        })}
        {orphanArtifacts.map((artifact) => {
          if (artifact.type === "table") return <TableArtifact key={artifact.id} artifact={artifact} />;
          if (artifact.type === "chart") return <ChartArtifact key={artifact.id} artifact={artifact} />;
          if (isSqlArtifact(artifact)) {
            const sql = sqlText(artifact);
            return (
              <section className="conv-sql-group" key={artifact.id}>
                <header>
                  <span className="conv-sql-title">
                    <Terminal size={13} />
                    {artifact.title}
                  </span>
                </header>
                <pre>{sql}</pre>
              </section>
            );
          }
          return null;
        })}
      </div>
    </details>
  );
}

function TableArtifact({ artifact }: { artifact: ConversationArtifact }) {
  const columns = tableColumns(artifact);
  const rows = tableRows(artifact).slice(0, 6);
  return (
    <div className="conv-table-artifact">
      <div className="conv-artifact-heading">
        <Table2 size={13} />
        <strong>{artifact.title}</strong>
      </div>
      {columns.length > 0 && rows.length > 0 && (
        <div className="conv-table-preview">
          <table>
            <thead>
              <tr>
                {columns.map((column) => <th key={column}>{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column, columnIndex) => (
                    <td key={column}>{cellText(row, column, columnIndex)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ChartArtifact({ artifact }: { artifact: ConversationArtifact }) {
  const series = chartSeries(artifact);
  const maxValue = Math.max(...series.map((item) => item.value), 1);
  return (
    <div className="conv-chart-artifact">
      <div className="conv-artifact-heading">
        <BarChart2 size={13} />
        <strong>{artifact.title}</strong>
      </div>
      {series.length > 0 && (
        <div className="conv-chart-preview">
          {series.slice(0, 8).map((item) => (
            <div className="conv-chart-row" key={item.label}>
              <span className="conv-chart-label">{item.label}</span>
              <span className="conv-chart-bar">
                <span style={{ width: `${Math.max(6, (item.value / maxValue) * 100)}%` }} />
              </span>
              <span className="conv-chart-value">{item.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
