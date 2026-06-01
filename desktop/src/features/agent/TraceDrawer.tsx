import { useState } from "react";
import type { AgentStep, AgentTraceEvent } from "../../lib/api";

interface TraceDrawerProps {
  steps: AgentStep[];
  traceEvents?: AgentTraceEvent[];
}

export function TraceDrawer({ steps, traceEvents = [] }: TraceDrawerProps) {
  const [open, setOpen] = useState(false);
  const events: AgentTraceEvent[] = traceEvents.length ? traceEvents : steps.map((step, index) => ({
    type: "agent.trace.step_completed" as const,
    event_id: `trace_${index + 1}_${step.name}_completed`,
    sequence: index + 1,
    step_id: `step_${index + 1}_${step.name}`,
    name: step.name,
    status: step.status,
    input: step.input,
    output: step.output,
    error: step.error,
    latency_ms: step.latency_ms,
  }));

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <button
        className="btn-ghost"
        onClick={() => setOpen((value) => !value)}
        style={{ width: "100%", justifyContent: "space-between", fontSize: "0.66rem" }}
      >
        <span>Trace</span>
        <span>{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 6 }}>
          {events.map((event) => (
            <details key={event.event_id || `${event.step_id}-${event.type}`} style={{ background: "#fff", padding: 6 }}>
              <summary style={{ cursor: "pointer" }}>
                {event.sequence ? `${event.sequence}. ` : ""}{event.name} - {event.status || "started"} - {event.latency_ms ?? 0}ms
              </summary>
              <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.62rem", overflowX: "auto" }}>
                {JSON.stringify(event, null, 2)}
              </pre>
            </details>
          ))}
        </div>
      ) : null}
    </section>
  );
}
