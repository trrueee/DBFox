import { BarChart2, Copy, Database, ExternalLink, LineChart, PieChart, Play, Table2, Terminal } from "lucide-react";
import type { CSSProperties } from "react";
import type { TableArtifact as TableArtifactModel, ResultViewArtifact as ResultViewArtifactModel } from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";

interface ArtifactEvidencePanelProps {
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: TableArtifactModel | ResultViewArtifactModel) => void;
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

function artifactKeys(artifact: ConversationArtifact): string[] {
  return [artifact.id, artifact.semantic_id].filter((item): item is string => Boolean(item));
}

function dependsOnAny(artifact: ConversationArtifact, keys: Set<string>): boolean {
  return dependsOn(artifact).some((id) => keys.has(id));
}

function groupedArtifacts(artifacts: ConversationArtifact[]) {
  const sql = artifacts
    .filter(isSqlArtifact)
    .sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
  return sql.map((sqlArtifact) => {
    const sqlKeys = new Set(artifactKeys(sqlArtifact));
    const safety = artifacts.filter(
      (item) => item.type === "safety" && dependsOnAny(item, sqlKeys),
    );
    const tables = artifacts.filter(
      (item) => (item.type === "table" || item.type === "result_view") && dependsOnAny(item, sqlKeys),
    );
    const tableIds = new Set(tables.flatMap(artifactKeys));
    const charts = artifacts.filter(
      (item) =>
        item.type === "chart" &&
        (dependsOnAny(item, sqlKeys) || dependsOnAny(item, tableIds)),
    );
    return { sql: sqlArtifact, safety, tables, charts };
  });
}

function tableRows(artifact: ConversationArtifact): unknown[] {
  const rows = artifact.payload.rows || artifact.payload.data || artifact.payload.previewRows;
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

function payloadNumber(payload: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  }
  return undefined;
}

function payloadString(payload: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

function payloadStringList(payload: Record<string, unknown>, keys: string[]): string[] | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (Array.isArray(value)) {
      const items = value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
      if (items.length > 0) return items;
    }
  }
  return undefined;
}

function payloadBoolean(payload: Record<string, unknown>, keys: string[]): boolean {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "boolean") return value;
  }
  return false;
}

function safetyGuardrailResult(payload: Record<string, unknown>): string {
  const flattened = payloadString(payload, ["guardrail_result", "guardrailResult"]);
  if (flattened) return flattened;
  const guardrail = payload.guardrail;
  if (guardrail && typeof guardrail === "object") {
    return payloadString(guardrail as Record<string, unknown>, ["result"]) || "unknown";
  }
  return "unknown";
}

function safetySchemaWarningsCount(payload: Record<string, unknown>): number {
  const count = payloadNumber(payload, ["schema_warnings_count", "schemaWarningsCount"]);
  if (count !== undefined) return count;
  if (Array.isArray(payload.schema_warnings)) return payload.schema_warnings.length;
  if (Array.isArray(payload.schemaWarnings)) return payload.schemaWarnings.length;
  return 0;
}

function toTableArtifactModel(artifact: ConversationArtifact): TableArtifactModel | ResultViewArtifactModel {
  const columns = tableColumns(artifact);
  const rows = tableRows(artifact).map((row) => columns.map((column, index) => cellText(row, column, index)));
  const rowCount = payloadNumber(artifact.payload, ["rowCount", "row_count"]) ?? rows.length;
  const returnedRows = payloadNumber(artifact.payload, ["returnedRows", "returned_rows"]) ?? rows.length;
  
  if (artifact.type === "result_view") {
    return {
      id: artifact.id,
      type: "result_view",
      title: artifact.title,
      storageMode: payloadString(artifact.payload, ["storageMode"]) === "sql_backed" ? "sql_backed" : "payload",
      datasourceId: payloadString(artifact.payload, ["datasourceId"]) || "",
      sourceSqlSemanticId: payloadString(artifact.payload, ["sourceSqlSemanticId"]) || "",
      sourceSql: payloadString(artifact.payload, ["sourceSql"]) || "",
      safeSql: payloadString(artifact.payload, ["safeSql"]) || "",
      columns,
      previewRows: payloadString(artifact.payload, ["storageMode"]) === "sql_backed" ? rows : rows.slice(0, 10),
      previewRowCount: payloadNumber(artifact.payload, ["previewRowCount"]) || Math.min(rows.length, 10),
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
  
  return {
    id: artifact.id,
    type: "table",
    title: artifact.title,
    columns,
    rows,
    rowCount,
    returnedRows,
    latencyMs: payloadNumber(artifact.payload, ["latencyMs", "latency_ms"]),
    sql: payloadString(artifact.payload, ["sql", "safe_sql"]),
    truncated: Boolean(artifact.payload.truncated),
    warnings: payloadStringList(artifact.payload, ["warnings"]),
    notices: payloadStringList(artifact.payload, ["notices"]),
    depends_on: artifact.depends_on,
    payload: artifact.payload,
  };
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

function chartType(artifact: ConversationArtifact): "bar" | "line" | "pie" {
  const value = artifact.payload.type || artifact.payload.chart_type || artifact.payload.kind;
  if (value === "line" || value === "pie") return value;
  return "bar";
}

function chartIcon(type: "bar" | "line" | "pie") {
  if (type === "line") return <LineChart size={13} />;
  if (type === "pie") return <PieChart size={13} />;
  return <BarChart2 size={13} />;
}

export function ArtifactEvidencePanel({ artifacts, onOpenSqlConsole, onOpenResultTab }: ArtifactEvidencePanelProps) {
  const groups = groupedArtifacts(artifacts);
  const groupedIds = new Set(groups.flatMap((group) => [
    group.sql.id,
    ...group.safety.map((item) => item.id),
    ...group.tables.map((item) => item.id),
    ...group.charts.map((item) => item.id),
  ]));
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
              {group.safety.map((safety) => <SafetyArtifact key={safety.id} artifact={safety} />)}
              {group.tables.map((table) => <TableArtifact key={table.id} artifact={table} onOpenResultTab={onOpenResultTab} />)}
              {group.charts.map((chart) => <ChartArtifact key={chart.id} artifact={chart} />)}
            </section>
          );
        })}
        {orphanArtifacts.map((artifact) => {
          if (artifact.type === "table" || artifact.type === "result_view") return <TableArtifact key={artifact.id} artifact={artifact} onOpenResultTab={onOpenResultTab} />;
          if (artifact.type === "chart") return <ChartArtifact key={artifact.id} artifact={artifact} />;
          if (artifact.type === "safety") return <SafetyArtifact key={artifact.id} artifact={artifact} />;
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

function SafetyArtifact({ artifact }: { artifact: ConversationArtifact }) {
  const canExecute = payloadBoolean(artifact.payload, ["can_execute", "canExecute"]);
  const requiresConfirmation = payloadBoolean(artifact.payload, ["requires_confirmation", "requiresConfirmation"]);
  const passed = payloadBoolean(artifact.payload, ["passed"]) || canExecute;
  const guardrail = safetyGuardrailResult(artifact.payload);
  const schemaWarnings = safetySchemaWarningsCount(artifact.payload);
  return (
    <div className={`conv-safety-artifact ${passed ? "is-safe" : "is-warning"}`}>
      <div className="conv-artifact-heading">
        <strong>安全检查</strong>
        <span>{canExecute ? "可执行" : "不可执行"}</span>
        <span>{requiresConfirmation ? "需要确认" : "无需确认"}</span>
      </div>
      <div className="conv-table-meta">
        <span>Guardrail: {guardrail}</span>
        <span>Schema warnings: {schemaWarnings}</span>
      </div>
    </div>
  );
}

function TableArtifact({
  artifact,
  onOpenResultTab,
}: {
  artifact: ConversationArtifact;
  onOpenResultTab?: (artifact: TableArtifactModel | ResultViewArtifactModel) => void;
}) {
  const columns = tableColumns(artifact);
  const allRows = tableRows(artifact);
  const rows = allRows.slice(0, 10);
  const rowCount = payloadNumber(artifact.payload, ["rowCount", "row_count"]) ?? allRows.length;
  const returnedRows = payloadNumber(artifact.payload, ["returnedRows", "returned_rows"]) ?? allRows.length;
  const latencyMs = payloadNumber(artifact.payload, ["latencyMs", "latency_ms"]);
  const truncated = Boolean(artifact.payload.truncated);
  return (
    <div className="conv-table-artifact">
      <div className="conv-artifact-heading">
        <Table2 size={13} />
        <strong>{artifact.title}</strong>
        {onOpenResultTab && (
          <button
            type="button"
            className="conv-artifact-open"
            onClick={() => onOpenResultTab(toTableArtifactModel(artifact))}
          >
            <ExternalLink size={12} />
            打开为 Tab
          </button>
        )}
      </div>
      {columns.length > 0 && rows.length > 0 && (
        <>
          <div className="conv-table-meta">
            <span>预览 {rows.length} / 共 {rowCount} 行</span>
            <span>{columns.length} 列</span>
            {latencyMs !== undefined && <span>{latencyMs}ms</span>}
            {returnedRows > rows.length && <span>已载入 {returnedRows} 行</span>}
            {truncated && <span className="conv-table-warning">结果已截断</span>}
          </div>
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
        </>
      )}
    </div>
  );
}

function ChartArtifact({ artifact }: { artifact: ConversationArtifact }) {
  const series = chartSeries(artifact);
  const maxValue = Math.max(...series.map((item) => item.value), 1);
  const type = chartType(artifact);
  return (
    <div className="conv-chart-artifact">
      <div className="conv-artifact-heading">
        {chartIcon(type)}
        <strong>{artifact.title}</strong>
      </div>
      {series.length > 0 && (
        <div className={`conv-chart-preview conv-chart-preview-${type}`}>
          {type === "line" ? (
            <LinePreview series={series} maxValue={maxValue} />
          ) : type === "pie" ? (
            <PiePreview series={series} />
          ) : (
            series.slice(0, 8).map((item) => (
              <div className="conv-chart-row" key={item.label}>
                <span className="conv-chart-label">{item.label}</span>
                <span className="conv-chart-bar">
                  <span style={{ width: `${Math.max(6, (item.value / maxValue) * 100)}%` }} />
                </span>
                <span className="conv-chart-value">{item.value}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function LinePreview({ series, maxValue }: { series: { label: string; value: number }[]; maxValue: number }) {
  const points = series.slice(0, 10).map((item, index, items) => {
    const x = items.length === 1 ? 50 : (index / (items.length - 1)) * 100;
    const y = 88 - (item.value / maxValue) * 72;
    return `${x},${y}`;
  }).join(" ");
  return (
    <>
      <svg viewBox="0 0 100 100" role="img" aria-label="Line chart preview">
        <polyline points={points} />
      </svg>
      <div className="conv-chart-legend">
        {series.slice(0, 4).map((item) => (
          <span key={item.label}>{item.label}: {item.value}</span>
        ))}
      </div>
    </>
  );
}

function PiePreview({ series }: { series: { label: string; value: number }[] }) {
  const total = series.reduce((sum, item) => sum + item.value, 0) || 1;
  const first = series[0];
  const firstPercent = Math.round((first.value / total) * 100);
  return (
    <>
      <div className="conv-pie-preview" style={{ "--pie-main": `${firstPercent}%` } as CSSProperties}>
        <span>{firstPercent}%</span>
      </div>
      <div className="conv-chart-legend">
        {series.slice(0, 4).map((item) => (
          <span key={item.label}>{item.label}: {item.value}</span>
        ))}
      </div>
    </>
  );
}
