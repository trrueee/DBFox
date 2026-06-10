import type { AgentRuntimeEvent, AgentStep } from "./types";
import { stepDisplayName } from "./stepDisplayNames";

type TimelineStatus = AgentStep["status"] | "running";

interface TimelineStep {
  name: string;
  status: TimelineStatus;
  latency_ms: number | null;
  error?: string | null;
}

interface AgentStepTimelineProps {
  steps: AgentStep[];
  runtimeEvents?: AgentRuntimeEvent[];
}

export function AgentStepTimeline({ steps, runtimeEvents = [] }: AgentStepTimelineProps) {
  const timeline = buildTimeline(steps, runtimeEvents);
  if (!timeline.length) return null;

  const completedCount = timeline.filter((step) => step.status === "success" || step.status === "skipped").length;
  const failedCount = timeline.filter((step) => step.status === "failed").length;
  const runningCount = timeline.filter((step) => step.status === "running").length;

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <strong>Step timeline</strong>
        <span style={{ color: "var(--text-muted)", fontSize: "0.62rem", whiteSpace: "nowrap" }}>
          {completedCount} done {runningCount ? `· ${runningCount} running` : ""}{failedCount ? `· ${failedCount} failed` : ""}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 7 }}>
        {timeline.map((step, index) => (
          <div
            key={`${step.name}-${index}`}
            style={{
              display: "grid",
              gridTemplateColumns: "18px minmax(0, 1fr) auto",
              alignItems: "center",
              gap: 7,
              minHeight: 24,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 8,
                height: 8,
                borderRadius: 8,
                background: statusColor(step.status),
                justifySelf: "center",
              }}
            />
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={`${step.name} (${stepDisplayName(step.name)})`}>
              {stepDisplayName(step.name)}
              <span style={{ display: "none" }}>{step.name}</span>
            </span>
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-sm ${statusClass(step.status)}`} style={{ fontSize: "0.58rem" }}>
              {step.status}
            </span>
            {step.error ? (
              <span style={{ gridColumn: "2 / 4", color: "var(--accent-red)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={step.error}>
                {step.error}
              </span>
            ) : step.latency_ms !== null ? (
              <span style={{ gridColumn: "2 / 4", color: "var(--text-muted)", fontSize: "0.58rem" }}>
                {step.latency_ms}ms
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function buildTimeline(steps: AgentStep[], runtimeEvents: AgentRuntimeEvent[]): TimelineStep[] {
  const timeline: TimelineStep[] = [];
  const indexByName = new Map<string, number>();

  const upsert = (step: TimelineStep) => {
    const existingIndex = indexByName.get(step.name);
    if (existingIndex === undefined) {
      indexByName.set(step.name, timeline.length);
      timeline.push(step);
      return;
    }
    timeline[existingIndex] = { ...timeline[existingIndex], ...step };
  };

  for (const step of steps) {
    upsert({
      name: step.name,
      status: step.status,
      latency_ms: step.latency_ms,
      error: step.error,
    });
  }

  for (const event of [...runtimeEvents].sort((left, right) => left.sequence - right.sequence)) {
    const name = typeof event.step?.name === "string" ? event.step.name : "";
    if (!name) continue;
    if (event.type === "agent.step.started") {
      upsert({ name, status: "running", latency_ms: null });
    }
    if (event.type === "agent.step.completed") {
      upsert({
        name,
        status: stepStatus(event.step?.status),
        latency_ms: typeof event.step?.latency_ms === "number" ? event.step.latency_ms : 0,
        error: typeof event.step?.error === "string" ? event.step.error : null,
      });
    }
  }

  return timeline;
}

function stepStatus(value: unknown): AgentStep["status"] {
  if (value === "failed" || value === "skipped") return value;
  return "success";
}

function statusClass(status: TimelineStatus) {
  if (status === "failed") return "bg-destructive/15 text-destructive";
  if (status === "running") return "bg-primary/10 text-primary";
  if (status === "skipped") return "bg-secondary text-secondary-foreground";
  return "bg-success/15 text-success";
}

function statusColor(status: TimelineStatus) {
  if (status === "failed") return "var(--accent-red)";
  if (status === "running") return "var(--accent-primary)";
  if (status === "skipped") return "var(--text-muted)";
  return "var(--accent-green)";
}
