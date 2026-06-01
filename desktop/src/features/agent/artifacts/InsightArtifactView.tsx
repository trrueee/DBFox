import type { AgentArtifact } from "../types";
import { SafetyStateBadge } from "../SafetyStateBadge";

function listValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

export function InsightArtifactView({ artifact }: { artifact: AgentArtifact }) {
  const facts = listValue(artifact.payload.notable_facts);
  const patterns = listValue(artifact.payload.detected_patterns);
  const limitations = listValue(artifact.payload.limitations);

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      {patterns.length ? <div style={{ color: "var(--text-muted)", marginTop: 4 }}>Patterns: {patterns.join(", ")}</div> : null}
      {facts.length ? (
        <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
          {facts.map((fact) => <li key={fact}>{fact}</li>)}
        </ul>
      ) : null}
      {limitations.length ? <div style={{ color: "var(--text-muted)", marginTop: 5 }}>Limitations: {limitations.join(" | ")}</div> : null}
      <SafetyStateBadge state={artifact.payload.safety_state} />
    </section>
  );
}
