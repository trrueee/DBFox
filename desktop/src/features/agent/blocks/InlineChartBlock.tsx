import type { AgentArtifact } from "../types";
import { SafetyStateBadge } from "../SafetyStateBadge";

export function InlineChartBlock({ artifact }: { artifact: AgentArtifact }) {
  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      <div style={{ display: "grid", gridTemplateColumns: "72px 1fr", gap: 4, marginTop: 5 }}>
        <span style={{ color: "var(--text-muted)" }}>Type</span>
        <span>{String(artifact.payload.type || "table")}</span>
        <span style={{ color: "var(--text-muted)" }}>X</span>
        <span>{String(artifact.payload.x || "-")}</span>
        <span style={{ color: "var(--text-muted)" }}>Y</span>
        <span>{String(artifact.payload.y || "-")}</span>
      </div>
      {artifact.payload.reason ? (
        <div style={{ color: "var(--text-muted)", marginTop: 5 }}>{String(artifact.payload.reason)}</div>
      ) : null}
      <SafetyStateBadge state={artifact.payload.safety_state} />
    </section>
  );
}
