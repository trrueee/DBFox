interface SafetyState {
  available?: boolean;
  passed?: boolean;
  can_execute?: boolean;
  requires_confirmation?: boolean;
  guardrail_result?: string | null;
  schema_warnings_count?: number;
}

export function SafetyStateBadge({ state }: { state: unknown }) {
  if (!state || typeof state !== "object" || !(state as SafetyState).available) return null;

  const safety = state as SafetyState;
  const isExecutable = Boolean(safety.can_execute);
  const className = isExecutable ? "status-badge-success" : "status-badge-error";
  const label = isExecutable ? "Safety: executable" : safety.requires_confirmation ? "Safety: confirmation required" : "Safety: blocked";
  const detail = [
    safety.guardrail_result ? `guardrail=${safety.guardrail_result}` : "",
    safety.schema_warnings_count ? `schema warnings=${safety.schema_warnings_count}` : "",
  ].filter(Boolean).join(" | ");

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginTop: 5 }}>
      <span className={`status-badge ${className}`}>{label}</span>
      {detail ? <span style={{ color: "var(--text-muted)", fontSize: "0.62rem" }}>{detail}</span> : null}
    </div>
  );
}
