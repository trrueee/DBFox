import { InlineSqlBlock } from "../blocks/InlineSqlBlock";
import type { AgentArtifact } from "../types";

interface SqlSuggestionArtifactViewProps {
  artifact: AgentArtifact;
  onOpenSql?: (sql: string) => void;
  onApplySql?: (sql: string) => void;
}

export function SqlSuggestionArtifactView({
  artifact,
  onOpenSql,
  onApplySql,
}: SqlSuggestionArtifactViewProps) {
  const payload = artifact.payload || {};
  const sql =
    (typeof payload.proposed_sql === "string" && payload.proposed_sql.trim()) ||
    (typeof payload.sql === "string" && payload.sql.trim()) ||
    "";
  const suggestions = Array.isArray(payload.suggestions) ? payload.suggestions : [];
  const answer = typeof payload.answer === "string" ? payload.answer : "";
  const producedBy = typeof payload.produced_by_step === "string" ? payload.produced_by_step : "";

  // If we have a concrete SQL, render with InlineSqlBlock
  if (sql) {
    return (
      <section>
        <InlineSqlBlock
          artifact={{
            ...artifact,
            payload: { ...payload, sql },
          }}
          onOpenSql={onOpenSql}
        />
        {onApplySql ? (
          <button
            className="btn-primary"
            onClick={() => onApplySql(sql)}
            style={{ marginTop: 4, fontSize: "0.62rem", padding: "2px 7px" }}
          >
            Apply to SQL Editor
          </button>
        ) : null}
      </section>
    );
  }

  // Render a list of suggestions
  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      {producedBy ? (
        <div style={{ fontSize: "0.58rem", color: "var(--text-muted)", marginTop: 2 }}>
          Produced by: {producedBy}
        </div>
      ) : null}
      {answer ? (
        <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{answer}</div>
      ) : null}
      {suggestions.length > 0 ? (
        <ul style={{ margin: "6px 0 0", paddingLeft: 16 }}>
          {suggestions.map((suggestion, i) => {
            const label =
              typeof suggestion === "object" && suggestion !== null
                ? (suggestion as Record<string, unknown>).label ||
                  (suggestion as Record<string, unknown>).question ||
                  JSON.stringify(suggestion)
                : String(suggestion);
            return <li key={i}>{String(label)}</li>;
          })}
        </ul>
      ) : null}
    </section>
  );
}
