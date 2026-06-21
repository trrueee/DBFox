import { Activity, CheckCircle2, Circle, Database, MessageSquare, Search, ShieldCheck, Wrench, XCircle } from "lucide-react";
import type { AgentRuntimeEvent } from "../../../lib/api/types";
import type { ConversationRun } from "../../../types/conversation";

export function RunTracePanel({ run }: { run: ConversationRun }) {
  const events = (run.events || []).filter((event) => String(event.type) !== "agent.answer.delta");
  const lastEvent = events[events.length - 1];
  const statusText = statusLabel(run.status);
  const summary = run.status === "running"
    ? lastEvent ? eventTitle(lastEvent) : "Analyzing..."
    : `Run ${statusText}`;

  return (
    <details className="conv-run-trace" open={run.status === "running"}>
      <summary>
        {run.status === "failed" ? <XCircle size={14} /> : <Activity size={14} />}
        <span>{summary}</span>
        {events.length > 0 && <span className="conv-run-count">{events.length}</span>}
      </summary>
      <div className="conv-run-trace-body">
        {events.length > 0 ? (
          <ol className="conv-run-events">
            {events.map((event) => (
              <li key={event.event_id || `${event.type}-${event.sequence}`}>
                <span className="conv-run-event-icon">{eventIcon(event)}</span>
                <span className="conv-run-event-copy">
                  <strong>{eventTitle(event)}</strong>
                  {eventSummary(event) && <span>{eventSummary(event)}</span>}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <div className="conv-run-empty">Waiting for runtime events...</div>
        )}
        <div className="conv-run-id">Run ID: {run.id}</div>
        {run.error_message && <div>{run.error_message}</div>}
      </div>
    </details>
  );
}

function statusLabel(status: ConversationRun["status"]): string {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "cancelled";
  if (status === "waiting_approval") return "waiting for approval";
  return "running";
}

function stepValue(event: AgentRuntimeEvent, key: string): string {
  const value = event.step?.[key];
  return typeof value === "string" ? value : "";
}

function eventTitle(event: AgentRuntimeEvent): string {
  const tool = stepValue(event, "tool_name") || stepValue(event, "tool");
  if (tool) return tool;
  const name = stepValue(event, "name") || stepValue(event, "step_name");
  if (name) return name;
  if (event.type === "agent.artifact.created") return event.artifact?.title || "Artifact created";
  if (event.type === "agent.answer.completed") return "Answer completed";
  if (event.type === "agent.run.started") return "Run started";
  if (event.type === "agent.run.completed") return "Run completed";
  if (event.type === "agent.run.failed") return "Run failed";
  return event.type.replace("agent.", "").replaceAll(".", " ");
}

function eventSummary(event: AgentRuntimeEvent): string {
  return (
    stepValue(event, "summary") ||
    stepValue(event, "message") ||
    stepValue(event, "status") ||
    event.error ||
    ""
  );
}

function eventIcon(event: AgentRuntimeEvent) {
  const title = eventTitle(event);
  if (event.type.includes("failed")) return <XCircle size={13} />;
  if (event.type.includes("completed")) return <CheckCircle2 size={13} />;
  if (title.includes("search") || title.includes("schema")) return <Search size={13} />;
  if (title.includes("sql") || title.includes("db") || title.includes("database")) return <Database size={13} />;
  if (title.includes("policy") || title.includes("safety")) return <ShieldCheck size={13} />;
  if (event.type === "agent.artifact.created") return <MessageSquare size={13} />;
  if (event.type.includes("step")) return <Wrench size={13} />;
  return <Circle size={13} />;
}
