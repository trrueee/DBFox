import { useCallback, useMemo, useState } from "react";
import { ChartArtifactView } from "./artifacts/ChartArtifactView";
import { ErrorArtifactView } from "./artifacts/ErrorArtifactView";
import { InsightArtifactView } from "./artifacts/InsightArtifactView";
import { PlanArtifactView } from "./artifacts/PlanArtifactView";
import { QueryPlanArtifactView } from "./artifacts/QueryPlanArtifactView";
import { RecommendationArtifactView } from "./artifacts/RecommendationArtifactView";
import { SafetyArtifactView } from "./artifacts/SafetyArtifactView";
import { SqlArtifactView } from "./artifacts/SqlArtifactView";
import { TableArtifactView } from "./artifacts/TableArtifactView";
import type { AgentArtifact, AgentWorkspaceContext } from "./types";

interface ArtifactInspectorProps {
  artifacts: AgentArtifact[];
  activeArtifactId?: string;
  onActiveArtifactChange?: (artifactId: string) => void;
  onOpenSql?: (sql: string) => void;
  onApplySql?: (sql: string) => void;
  onAsk?: (question: string, workspaceContext?: AgentWorkspaceContext | null) => void;
  workspaceContext?: AgentWorkspaceContext | null;
}

export function ArtifactInspector({
  artifacts,
  activeArtifactId,
  onActiveArtifactChange,
  onOpenSql,
  onApplySql,
  onAsk,
  workspaceContext,
}: ArtifactInspectorProps) {
  const dockArtifacts = useMemo(() => artifacts.filter((artifact) => artifact.presentation.mode !== "hidden"), [artifacts]);
  const [localActiveId, setLocalActiveId] = useState(dockArtifacts[0]?.id || "");
  const selectedId = activeArtifactId ?? localActiveId;
  const active = dockArtifacts.find((artifact) => artifact.id === selectedId) || dockArtifacts[0];

  const selectArtifact = useCallback((artifactId: string) => {
    setLocalActiveId(artifactId);
    onActiveArtifactChange?.(artifactId);
  }, [onActiveArtifactChange]);

  if (!dockArtifacts.length || !active) return null;
  const actionableSql = extractActionableSql(active);
  const sqlActionContext = buildArtifactWorkspaceContext(workspaceContext, active, actionableSql);

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <strong>Artifact Inspector</strong>
        <button
          className="btn-secondary"
          onClick={() => exportArtifact(active)}
          style={{ fontSize: "0.62rem", padding: "2px 7px" }}
        >
          Export
        </button>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 6 }}>
        {dockArtifacts.map((artifact) => (
          <button
            key={artifact.id}
            className={artifact.id === active.id ? "btn-primary" : "btn-secondary"}
            onClick={() => selectArtifact(artifact.id)}
            style={{ fontSize: "0.62rem", padding: "2px 7px" }}
            title={artifact.id}
          >
            {artifact.title}
          </button>
        ))}
      </div>
      <div style={{ marginTop: 8 }}>
        {actionableSql ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 6 }}>
            {onApplySql ? (
              <button
                className="btn-primary"
                onClick={() => onApplySql(actionableSql)}
                style={{ fontSize: "0.62rem", padding: "2px 7px" }}
              >
                Apply to SQL Editor
              </button>
            ) : null}
            {onOpenSql ? (
              <button
                className="btn-secondary"
                onClick={() => onOpenSql(actionableSql)}
                style={{ fontSize: "0.62rem", padding: "2px 7px" }}
              >
                Open SQL
              </button>
            ) : null}
            {onAsk ? (
              <>
                <button
                  className="btn-secondary"
                  onClick={() => onAsk("Explain this SQL", sqlActionContext)}
                  style={{ fontSize: "0.62rem", padding: "2px 7px" }}
                >
                  Explain SQL
                </button>
                <button
                  className="btn-secondary"
                  onClick={() => onAsk("Revise this SQL", sqlActionContext)}
                  style={{ fontSize: "0.62rem", padding: "2px 7px" }}
                >
                  Revise SQL
                </button>
              </>
            ) : null}
            <button
              className="btn-secondary"
              onClick={() => void navigator.clipboard?.writeText(actionableSql)}
              style={{ fontSize: "0.62rem", padding: "2px 7px" }}
            >
              Copy SQL
            </button>
          </div>
        ) : null}
        <ArtifactView artifact={active} onOpenSql={onOpenSql} onAsk={onAsk} workspaceContext={sqlActionContext} />
      </div>
    </section>
  );
}

function extractActionableSql(artifact: AgentArtifact): string {
  const payload = artifact.payload || {};
  for (const key of ["proposed_sql", "sql", "safe_sql"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  const suggestions = payload.suggestions;
  if (Array.isArray(suggestions)) {
    for (const suggestion of suggestions) {
      if (suggestion && typeof suggestion === "object" && "proposed_sql" in suggestion) {
        const sql = (suggestion as { proposed_sql?: unknown }).proposed_sql;
        if (typeof sql === "string" && sql.trim()) return sql.trim();
      }
    }
  }
  return "";
}

function buildArtifactWorkspaceContext(
  base: AgentWorkspaceContext | null | undefined,
  artifact: AgentArtifact,
  sql: string,
): AgentWorkspaceContext | null {
  if (!base) return null;
  return {
    ...base,
    selected_artifact_id: artifact.id,
    selected_sql: sql || base.selected_sql,
    active_sql: sql || base.active_sql,
  };
}

function exportArtifact(artifact: AgentArtifact) {
  const { content, extension, mimeType } = serializeArtifact(artifact);
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `databox-${artifact.id}.${extension}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function serializeArtifact(artifact: AgentArtifact): { content: string; extension: string; mimeType: string } {
  if (artifact.type === "sql" && typeof artifact.payload.sql === "string") {
    return { content: artifact.payload.sql, extension: "sql", mimeType: "text/sql;charset=utf-8" };
  }
  if (artifact.type === "table") {
    return { content: serializeTableArtifact(artifact), extension: "csv", mimeType: "text/csv;charset=utf-8" };
  }
  return {
    content: JSON.stringify(
      { id: artifact.id, type: artifact.type, title: artifact.title, payload: artifact.payload, refs: artifact.refs || {} },
      null,
      2,
    ),
    extension: "json",
    mimeType: "application/json;charset=utf-8",
  };
}

function serializeTableArtifact(artifact: AgentArtifact): string {
  const columns = Array.isArray(artifact.payload.columns) ? artifact.payload.columns.map(String) : [];
  const rows = Array.isArray(artifact.payload.rows)
    ? (artifact.payload.rows.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object") as Array<Record<string, unknown>>)
    : [];
  return [
    columns.map(csvCell).join(","),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
  ].join("\n");
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function ArtifactView({
  artifact,
  onOpenSql,
  onAsk,
  workspaceContext,
}: {
  artifact: AgentArtifact;
  onOpenSql?: (sql: string) => void;
  onAsk?: (question: string, workspaceContext?: AgentWorkspaceContext | null) => void;
  workspaceContext?: AgentWorkspaceContext | null;
}) {
  if (artifact.type === "agent_plan") return <PlanArtifactView artifact={artifact} />;
  if (artifact.type === "table") return <TableArtifactView artifact={artifact} />;
  if (artifact.type === "chart") return <ChartArtifactView artifact={artifact} />;
  if (artifact.type === "sql") return <SqlArtifactView artifact={artifact} onOpenSql={onOpenSql} />;
  if (artifact.type === "safety") return <SafetyArtifactView artifact={artifact} />;
  if (artifact.type === "query_plan") return <QueryPlanArtifactView artifact={artifact} />;
  if (artifact.type === "insight") return <InsightArtifactView artifact={artifact} />;
  if (artifact.type === "recommendation") {
    return <RecommendationArtifactView artifact={artifact} onAsk={onAsk} workspaceContext={workspaceContext} />;
  }
  if (artifact.type === "error") return <ErrorArtifactView artifact={artifact} />;

  return (
    <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.64rem", background: "#fff", padding: 8, overflowX: "auto" }}>
      {JSON.stringify(artifact.payload, null, 2)}
    </pre>
  );
}
