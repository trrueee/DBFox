import type { AgentTaskLens } from "../../lib/api";

interface AgentTaskLensProps {
  taskLens?: AgentTaskLens | null;
  compact?: boolean;
}

export function AgentTaskLensPanel({ taskLens, compact = false }: AgentTaskLensProps) {
  if (!taskLens) return null;

  const focus = taskLens.current_focus?.trim();
  const goal = taskLens.goal?.trim();
  const next = taskLens.next_likely?.trim();
  const missing = (taskLens.missing_evidence || []).filter(Boolean);

  if (!focus && !goal && !next && !missing.length) return null;

  return (
    <div
      style={{
        marginTop: compact ? 4 : 6,
        padding: compact ? "4px 6px" : "6px 8px",
        background: "var(--bg-primary)",
        border: "1px solid var(--border-light)",
        borderRadius: 4,
        fontSize: compact ? "0.58rem" : "0.6rem",
        lineHeight: 1.4,
      }}
    >
      <div style={{ fontWeight: 600, color: "var(--text-muted)", marginBottom: 3 }}>
        Task Lens
      </div>
      {goal ? (
        <div style={{ color: "var(--text-muted)" }}>
          <span style={{ fontWeight: 500 }}>Goal:</span> {goal}
        </div>
      ) : null}
      {focus ? (
        <div style={{ marginTop: 2, color: "var(--text-primary)", fontWeight: 500 }}>
          {focus}
        </div>
      ) : null}
      {next ? (
        <div style={{ marginTop: 2, color: "var(--text-muted)" }}>
          <span style={{ fontWeight: 500 }}>Next:</span> {next}
        </div>
      ) : null}
      {missing.length > 0 ? (
        <div style={{ marginTop: 2, color: "var(--text-muted)" }}>
          <span style={{ fontWeight: 500 }}>Missing:</span> {missing.join(", ")}
        </div>
      ) : null}
    </div>
  );
}
