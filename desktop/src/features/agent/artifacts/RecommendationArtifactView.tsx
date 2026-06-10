import type { AgentArtifact, AgentWorkspaceContext } from "../types";

interface RecommendationArtifactViewProps {
  artifact: AgentArtifact;
  onAsk?: (question: string, workspaceContext?: AgentWorkspaceContext | null) => void;
  workspaceContext?: AgentWorkspaceContext | null;
}

export function RecommendationArtifactView({ artifact, onAsk, workspaceContext }: RecommendationArtifactViewProps) {
  const recommendations = listOfStrings(artifact.payload.recommendations);
  const followUps = listOfStrings(artifact.payload.followUpQuestions).length
    ? listOfStrings(artifact.payload.followUpQuestions)
    : listOfStrings(artifact.payload.follow_up_questions);
  const isEmpty = !recommendations.length && !followUps.length;

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      {isEmpty ? (
        <div style={{ marginTop: 6, color: "var(--text-muted)" }}>No recommendations yet.</div>
      ) : (
        <>
          {recommendations.length ? (
            <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
              {recommendations.map((recommendation) => <li key={recommendation}>{recommendation}</li>)}
            </ul>
          ) : null}
          {followUps.length ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 7 }}>
              {followUps.map((question) => (
                <div
                  key={question}
                  style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", alignItems: "center", gap: 6 }}
                >
                  <span>{question}</span>
                  {onAsk ? (
                    <button
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground transition-colors"
                      type="button"
                      aria-label={`Ask follow-up: ${question}`}
                      onClick={() => onAsk(question, workspaceContext)}
                      style={{ fontSize: "0.62rem", padding: "2px 7px" }}
                    >
                      Ask
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

function listOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).map((item) => item.trim()).filter(Boolean) : [];
}
