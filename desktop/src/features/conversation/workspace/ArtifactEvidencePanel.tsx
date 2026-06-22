import { Copy, Database, ExternalLink, Play, Table2, Terminal } from "lucide-react";
import type {
  TableArtifact as TableArtifactModel,
  ResultViewArtifact as ResultViewArtifactModel,
} from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";
import { ChartArtifactView } from "../../workspace/artifacts/ChartArtifactView";
import {
  conversationArtifactKeys,
  conversationCellText,
  conversationSqlText,
  conversationTableColumns,
  conversationTableRows,
  dependsOnAnyConversationArtifact,
  isSqlConversationArtifact,
  payloadBoolean,
  payloadNumber,
  safetyGuardrailResult,
  safetySchemaWarningsCount,
  sortConversationArtifacts,
  toChartArtifactModel,
  toTableArtifactModel,
} from "./conversationArtifactModels";

interface ArtifactEvidencePanelProps {
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: TableArtifactModel | ResultViewArtifactModel) => void;
}

function groupedArtifacts(artifacts: ConversationArtifact[]) {
  const sql = sortConversationArtifacts(artifacts.filter(isSqlConversationArtifact));
  return sql.map((sqlArtifact) => {
    const sqlKeys = new Set(conversationArtifactKeys(sqlArtifact));
    const safety = artifacts.filter(
      (item) => item.type === "safety" && dependsOnAnyConversationArtifact(item, sqlKeys),
    );
    const tables = artifacts.filter(
      (item) => (item.type === "table" || item.type === "result_view") && dependsOnAnyConversationArtifact(item, sqlKeys),
    );
    const tableIds = new Set(tables.flatMap(conversationArtifactKeys));
    const charts = artifacts.filter(
      (item) =>
        item.type === "chart" &&
        (dependsOnAnyConversationArtifact(item, sqlKeys) || dependsOnAnyConversationArtifact(item, tableIds)),
    );
    return { sql: sqlArtifact, safety, tables, charts };
  });
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
          const sql = conversationSqlText(group.sql);
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
          if (isSqlConversationArtifact(artifact)) {
            const sql = conversationSqlText(artifact);
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
  const columns = conversationTableColumns(artifact);
  const allRows = conversationTableRows(artifact);
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
                      <td key={column}>{conversationCellText(row, column, columnIndex)}</td>
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
  return <ChartArtifactView artifact={toChartArtifactModel(artifact)} onToast={() => undefined} compact />;
}
