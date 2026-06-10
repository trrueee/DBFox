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
          <button className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors" onClick={() => onOpenSql(sql)} style={{ fontSize: "0.64rem" }}>
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
