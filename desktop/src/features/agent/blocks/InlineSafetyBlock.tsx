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
  const rewriteNotes = Array.isArray(payload.rewrite_notes) ? payload.rewrite_notes.map(compactValue) : [];

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      <div style={{ display: "grid", gridTemplateColumns: "82px 1fr", gap: 3, marginTop: 5 }}>
        <span>Passed</span><span>{compactValue(payload.passed)}</span>
        <span>Can execute</span><span>{compactValue(payload.can_execute)}</span>
        <span>Confirm</span><span>{compactValue(payload.requires_confirmation)}</span>
      </div>
      {rewriteNotes.length ? <div style={{ marginTop: 5, color: "var(--text-muted)" }}>Rewrite: {rewriteNotes.join(" | ")}</div> : null}
      {messages.length ? <div style={{ marginTop: 3, color: "var(--text-muted)" }}>Messages: {messages.join(" | ")}</div> : null}
    </section>
  );
}
