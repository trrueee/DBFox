import type { AgentArtifact } from "../types";

function compactValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function InlineSafetyBlock({ artifact }: { artifact: AgentArtifact }) {
  const payload = artifact.payload;
  const messages = Array.isArray(payload.messages) ? payload.messages.map(compactValue) : [];
  const blockedReasons = Array.isArray(payload.blocked_reasons) ? payload.blocked_reasons.map(compactValue) : [];
  const rewriteNotes = Array.isArray(payload.rewrite_notes) ? payload.rewrite_notes.map(compactValue) : [];
  const safeSql = typeof payload.safe_sql === "string" ? payload.safe_sql.trim() : "";

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(132px, auto) 1fr", gap: 3, marginTop: 5 }}>
        <span>Passed</span><span>{compactValue(payload.passed)}</span>
        <span>Can execute</span><span>{compactValue(payload.can_execute)}</span>
        <span>Requires confirmation</span><span>{compactValue(payload.requires_confirmation)}</span>
        <span>Blocked reasons</span><span>{blockedReasons.length ? blockedReasons.join(" | ") : "-"}</span>
        <span>Messages</span><span>{messages.length ? messages.join(" | ") : "-"}</span>
      </div>
      {rewriteNotes.length ? <div style={{ marginTop: 5, color: "var(--text-muted)" }}>Rewrite: {rewriteNotes.join(" | ")}</div> : null}
      {safeSql ? (
        <div style={{ marginTop: 7 }}>
          <strong style={{ fontSize: "0.62rem" }}>Safe SQL</strong>
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.64rem", background: "#fff", padding: 6, margin: "4px 0 0", overflowX: "auto" }}>
            {safeSql}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
