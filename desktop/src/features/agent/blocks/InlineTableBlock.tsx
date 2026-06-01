import type { AgentArtifact } from "../types";
import { SafetyStateBadge } from "../SafetyStateBadge";

function compactValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function InlineTableBlock({ artifact }: { artifact: AgentArtifact }) {
  const columns = Array.isArray(artifact.payload.columns) ? artifact.payload.columns.map(String) : [];
  const rows = Array.isArray(artifact.payload.rows)
    ? (artifact.payload.rows.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object") as Array<Record<string, unknown>>)
    : [];

  if (!columns.length || !rows.length) return null;

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <strong>{artifact.title}</strong>
      <div style={{ color: "var(--text-muted)", marginTop: 3, fontSize: "0.64rem" }}>
        {compactValue(artifact.payload.rowCount)} rows
      </div>
      <SafetyStateBadge state={artifact.payload.safety_state} />
      <div style={{ overflow: "auto", maxHeight: 180, marginTop: 6, background: "#fff" }}>
        <table className="data-table">
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, 12).map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => (
                  <td key={`${rowIndex}-${column}`}>{compactValue(row[column])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
