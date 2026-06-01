import { SafetyStateBadge } from "../SafetyStateBadge";
import type { AgentArtifact } from "../types";

export function ErrorArtifactView({ artifact }: { artifact: AgentArtifact }) {
  const error = String(artifact.payload.error || "Agent stopped.");
  const recovery = artifact.payload.recovery_guidance ? String(artifact.payload.recovery_guidance) : "";

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      <div style={{ marginTop: 5, color: "var(--accent-red)", lineHeight: 1.5 }}>{error}</div>
      {recovery ? (
        <div style={{ marginTop: 6 }}>
          <strong style={{ fontSize: "0.64rem" }}>Recovery</strong>
          <div style={{ marginTop: 3, color: "var(--text-secondary)", lineHeight: 1.5 }}>{recovery}</div>
        </div>
      ) : null}
      <SafetyStateBadge state={artifact.payload.safety_state} />
    </section>
  );
}
