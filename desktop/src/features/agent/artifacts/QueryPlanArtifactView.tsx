import type { AgentArtifact } from "../types";

export function QueryPlanArtifactView({ artifact }: { artifact: AgentArtifact }) {
  return (
    <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.64rem", background: "#fff", padding: 8, overflowX: "auto" }}>
      {JSON.stringify(artifact.payload, null, 2)}
    </pre>
  );
}
