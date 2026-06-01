import { useEffect, useState } from "react";
import { ChartArtifactView } from "./artifacts/ChartArtifactView";
import { ErrorArtifactView } from "./artifacts/ErrorArtifactView";
import { InsightArtifactView } from "./artifacts/InsightArtifactView";
import { QueryPlanArtifactView } from "./artifacts/QueryPlanArtifactView";
import { SafetyArtifactView } from "./artifacts/SafetyArtifactView";
import { SqlArtifactView } from "./artifacts/SqlArtifactView";
import { TableArtifactView } from "./artifacts/TableArtifactView";
import type { AgentArtifact } from "./types";

interface ArtifactInspectorProps {
  artifacts: AgentArtifact[];
  activeArtifactId?: string;
  onActiveArtifactChange?: (artifactId: string) => void;
  onOpenSql?: (sql: string) => void;
}

export function ArtifactInspector({ artifacts, activeArtifactId, onActiveArtifactChange, onOpenSql }: ArtifactInspectorProps) {
  const dockArtifacts = artifacts.filter((artifact) => artifact.presentation.mode !== "hidden");
  const [localActiveId, setLocalActiveId] = useState(dockArtifacts[0]?.id || "");
  const selectedId = activeArtifactId ?? localActiveId;
  const active = dockArtifacts.find((artifact) => artifact.id === selectedId) || dockArtifacts[0];
  const dockArtifactIds = dockArtifacts.map((artifact) => artifact.id).join("|");

  useEffect(() => {
    if (!dockArtifacts.length) return;
    if (selectedId && dockArtifacts.some((artifact) => artifact.id === selectedId)) return;
    selectArtifact(dockArtifacts[0].id);
  }, [dockArtifactIds, selectedId]);

  if (!dockArtifacts.length || !active) return null;

  function selectArtifact(artifactId: string) {
    setLocalActiveId(artifactId);
    onActiveArtifactChange?.(artifactId);
  }

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
        <ArtifactView artifact={active} onOpenSql={onOpenSql} />
      </div>
    </section>
  );
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

function ArtifactView({ artifact, onOpenSql }: { artifact: AgentArtifact; onOpenSql?: (sql: string) => void }) {
  if (artifact.type === "table") return <TableArtifactView artifact={artifact} />;
  if (artifact.type === "chart") return <ChartArtifactView artifact={artifact} />;
  if (artifact.type === "sql") return <SqlArtifactView artifact={artifact} onOpenSql={onOpenSql} />;
  if (artifact.type === "safety") return <SafetyArtifactView artifact={artifact} />;
  if (artifact.type === "query_plan") return <QueryPlanArtifactView artifact={artifact} />;
  if (artifact.type === "insight") return <InsightArtifactView artifact={artifact} />;
  if (artifact.type === "error") return <ErrorArtifactView artifact={artifact} />;

  return (
    <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.64rem", background: "#fff", padding: 8, overflowX: "auto" }}>
      {JSON.stringify(artifact.payload, null, 2)}
    </pre>
  );
}
