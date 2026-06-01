import type { AgentArtifact } from "../types";
import { SafetyStateBadge } from "../SafetyStateBadge";

export function InlineSqlBlock({ artifact, onOpenSql }: { artifact: AgentArtifact; onOpenSql?: (sql: string) => void }) {
  const sql = String(artifact.payload.sql || "");
  if (!sql) return null;

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <strong>{artifact.title}</strong>
        {onOpenSql ? (
          <button className="btn-ghost" onClick={() => onOpenSql(sql)} style={{ fontSize: "0.64rem" }}>
            Open
          </button>
        ) : null}
      </div>
      <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.64rem", background: "#fff", padding: 6, marginTop: 5, overflowX: "auto" }}>
        {sql}
      </pre>
      <SafetyStateBadge state={artifact.payload.safety_state} />
    </section>
  );
}
