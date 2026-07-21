import { Copy, Database, ExternalLink, Play, Table2, Terminal } from "lucide-react";
import type { ResultViewArtifact as ResultViewArtifactModel } from "../../../types/agentArtifact";
import type { ConversationArtifact } from "../../../types/conversation";
import { safetyCheckLabel } from "../../../lib/presentation";
import { DeferredChartArtifactView } from "../../workspace/artifacts/DeferredChartArtifactView";
import {
  conversationArtifactKeys,
  conversationSqlText,
  conversationTableColumns,
  dependsOnAnyConversationArtifact,
  isSqlBackedResultViewArtifact,
  isSqlConversationArtifact,
  payloadBoolean,
  payloadNumber,
  safetyRedactionSummary,
  safetyGuardrailResult,
  safetySchemaWarningsCount,
  sortConversationArtifacts,
  toChartArtifactModel,
  toResultViewArtifactModel,
} from "./conversationArtifactModels";

interface ArtifactEvidencePanelProps {
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifactModel) => void;
}

function groupedArtifacts(artifacts: ConversationArtifact[]) {
  const sql = sortConversationArtifacts(artifacts.filter(isSqlConversationArtifact));
  return sql.map((sqlArtifact) => {
    const sqlKeys = new Set(conversationArtifactKeys(sqlArtifact));
    const safety = artifacts.filter(
      (item) => item.type === "safety" && dependsOnAnyConversationArtifact(item, sqlKeys),
    );
    const tables = artifacts.filter(
      (item) => isSqlBackedResultViewArtifact(item) && dependsOnAnyConversationArtifact(item, sqlKeys),
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
              {group.tables.map((table) => <ResultViewArtifactCard key={table.id} artifact={table} onOpenResultTab={onOpenResultTab} />)}
              {group.charts.map((chart) => <ChartArtifact key={chart.id} artifact={chart} />)}
            </section>
          );
        })}
        {orphanArtifacts.map((artifact) => {
          if (isSqlBackedResultViewArtifact(artifact)) return <ResultViewArtifactCard key={artifact.id} artifact={artifact} onOpenResultTab={onOpenResultTab} />;
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
  const canExecute = payloadBoolean(artifact.payload, ["canExecute"]);
  const requiresApproval = payloadBoolean(artifact.payload, ["requiresApproval"]);
  const passed = payloadBoolean(artifact.payload, ["passed"]) || canExecute;
  const guardrail = safetyGuardrailResult(artifact.payload);
  const schemaWarnings = safetySchemaWarningsCount(artifact.payload);
  const redaction = safetyRedactionSummary(artifact.payload);
  return (
    <div className={`conv-safety-artifact ${passed ? "is-safe" : "is-warning"}`}>
      <div className="conv-artifact-heading">
        <strong>安全检查</strong>
        <span>{canExecute ? "可执行" : "不可执行"}</span>
        <span>{requiresApproval ? "需要批准" : "无需批准"}</span>
      </div>
      <div className="conv-table-meta">
        <span>安全策略：{safetyCheckLabel(guardrail)}</span>
        <span>表结构提醒：{schemaWarnings}</span>
      </div>
      {redaction.count > 0 && (
        <div className="conv-safety-redaction">
          <strong>已脱敏 {redaction.count} 个字段</strong>
          {redaction.fields.length > 0 && <span>{redaction.fields.join(", ")}</span>}
        </div>
      )}
    </div>
  );
}

function ResultViewArtifactCard({
  artifact,
  onOpenResultTab,
}: {
  artifact: ConversationArtifact;
  onOpenResultTab?: (artifact: ResultViewArtifactModel) => void;
}) {
  const columns = conversationTableColumns(artifact);
  const rowCount = payloadNumber(artifact.payload, ["rowCount"]);
  const returnedRows = payloadNumber(artifact.payload, ["returnedRows"]);
  const latencyMs = payloadNumber(artifact.payload, ["latencyMs"]);
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
            onClick={() => onOpenResultTab(toResultViewArtifactModel(artifact))}
          >
            <ExternalLink size={12} />
            打开为 Tab
          </button>
        )}
      </div>
      <div className="conv-table-meta">
        {rowCount !== undefined && <span>共 {rowCount} 行</span>}
        <span>{columns.length} 列</span>
        {latencyMs !== undefined && <span>{latencyMs}ms</span>}
        {returnedRows !== undefined && <span>执行返回 {returnedRows} 行</span>}
        {truncated && <span className="conv-table-warning">执行结果已截断</span>}
        <span>打开工件后按需读取数据</span>
      </div>
    </div>
  );
}

function ChartArtifact({ artifact }: { artifact: ConversationArtifact }) {
  return <DeferredChartArtifactView artifact={toChartArtifactModel(artifact)} onToast={() => undefined} compact />;
}
