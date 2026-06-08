import type { AgentArtifact } from "../types";

interface PlanStepView {
  id: string;
  title: string;
  status: string;
  tool_name?: string | null;
  depends_on?: string[];
}

export function PlanArtifactView({ artifact }: { artifact: AgentArtifact }) {
  const steps = planSteps(artifact.payload.steps);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <strong>Plan checklist</strong>
        <span style={{ color: "var(--text-muted)", fontSize: "0.6rem" }}>{steps.length} steps</span>
      </div>
      {steps.length ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {steps.map((step) => (
            <div
              key={step.id}
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                gap: 6,
                padding: 7,
                background: "#fff",
                border: "1px solid var(--border-light)",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={step.title}>
                  {step.title}
                </div>
                {step.tool_name ? (
                  <div style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: "0.6rem" }}>
                    {step.tool_name}
                  </div>
                ) : null}
                {step.depends_on?.length ? (
                  <div style={{ color: "var(--text-muted)", fontSize: "0.6rem" }}>
                    depends on {step.depends_on.join(", ")}
                  </div>
                ) : null}
              </div>
              <span className={`status-badge ${statusClass(step.status)}`} style={{ fontSize: "0.58rem", alignSelf: "start" }}>
                {step.status}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ color: "var(--text-muted)" }}>No plan steps yet.</div>
      )}
    </section>
  );
}

function planSteps(value: unknown): PlanStepView[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => ({
      id: stringValue(item.id) || stringValue(item.title) || "step",
      title: stringValue(item.title) || stringValue(item.id) || "Untitled step",
      status: stringValue(item.status) || "pending",
      tool_name: stringValue(item.tool_name),
      depends_on: Array.isArray(item.depends_on) ? item.depends_on.map(String).filter(Boolean) : [],
    }));
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function statusClass(status: string): string {
  if (status === "failed") return "status-badge-error";
  if (status === "running" || status === "waiting_approval") return "status-badge-info";
  if (status === "skipped" || status === "pending") return "status-badge-neutral";
  return "status-badge-success";
}
