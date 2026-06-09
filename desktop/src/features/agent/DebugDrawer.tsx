import { useState } from "react";
import { X } from "lucide-react";
import type {
  AgentRunResponse,
  AgentRuntimeEvent,
  AgentStep,
  AgentTraceEvent,
  AgentWorkspaceContext,
} from "../../lib/api";

interface DebugDrawerProps {
  open: boolean;
  onClose: () => void;
  workspaceContext?: AgentWorkspaceContext | null;
  response?: AgentRunResponse | null;
  steps?: AgentStep[];
  traceEvents?: AgentTraceEvent[];
  runtimeEvents?: AgentRuntimeEvent[];
}

type DebugTab = "state" | "trace" | "tools" | "policy" | "events" | "raw";

const TABS: { key: DebugTab; label: string }[] = [
  { key: "state", label: "State" },
  { key: "trace", label: "Trace" },
  { key: "tools", label: "Tool calls" },
  { key: "policy", label: "Policy" },
  { key: "events", label: "Events" },
  { key: "raw", label: "Raw response" },
];

export function DebugDrawer({
  open,
  onClose,
  workspaceContext,
  response,
  steps,
  traceEvents,
  runtimeEvents,
}: DebugDrawerProps) {
  const [tab, setTab] = useState<DebugTab>("state");

  if (!open) return null;

  const isHidden =
    typeof import.meta !== "undefined" &&
    (import.meta as Record<string, unknown>).env?.VITE_DATABOX_DEBUG_AGENT === "false";

  return (
    <div className="debug-drawer">
      <div className="debug-drawer-header">
        <span className="debug-drawer-title">Debug Panel</span>
        <button className="btn-ghost" onClick={onClose} style={{ padding: 2 }}>
          <X size={12} />
        </button>
      </div>

      <div className="debug-drawer-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`debug-tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
            type="button"
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="debug-drawer-body">
        {tab === "state" && (
          <DebugJsonSection
            title="WorkspaceContext"
            data={workspaceContext}
          />
        )}
        {tab === "trace" && (
          <DebugTraceSection events={traceEvents || []} />
        )}
        {tab === "tools" && (
          <DebugToolsSection steps={steps || []} events={runtimeEvents || []} />
        )}
        {tab === "policy" && (
          <DebugJsonSection
            title="Policy Decision"
            data={
              response?.approval?.policy_decision ||
              (steps?.length
                ? steps.find(
                    (s) =>
                      s.name === "validate_sql" || s.name === "policy_check",
                  )
                : null)
            }
          />
        )}
        {tab === "events" && (
          <DebugEventsSection events={runtimeEvents || []} />
        )}
        {tab === "raw" && (
          <DebugJsonSection title="AgentRunResponse" data={response} />
        )}
      </div>
    </div>
  );
}

function DebugJsonSection({
  title,
  data,
}: {
  title: string;
  data?: unknown;
}) {
  return (
    <div className="debug-section">
      <div className="debug-section-title">{title}</div>
      <pre className="debug-json">
        {data ? JSON.stringify(data, null, 2) : "(empty)"}
      </pre>
    </div>
  );
}

function DebugTraceSection({ events }: { events: AgentTraceEvent[] }) {
  if (!events.length) {
    return <div className="debug-empty">No trace events</div>;
  }
  return (
    <div className="debug-section">
      <div className="debug-section-title">Trace Events ({events.length})</div>
      <div className="debug-list">
        {events.map((event, i) => (
          <div key={i} className="debug-list-item">
            <span className="debug-list-type">{event.type}</span>
            <span className="debug-list-name">
              {typeof event.step?.name === "string" ? event.step.name : "-"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function DebugToolsSection({
  steps,
  events,
}: {
  steps: AgentStep[];
  events: AgentRuntimeEvent[];
}) {
  return (
    <div className="debug-section">
      <div className="debug-section-title">Tool Calls</div>
      <div className="debug-list">
        {steps
          .filter((s) => s.input || s.output)
          .map((step, i) => (
            <details key={i} className="debug-detail">
              <summary>
                {step.name} — {step.status}
              </summary>
              {step.input && (
                <div>
                  <strong>Input:</strong>
                  <pre className="debug-json">
                    {JSON.stringify(step.input, null, 2)}
                  </pre>
                </div>
              )}
              {step.output && (
                <div>
                  <strong>Output:</strong>
                  <pre className="debug-json">
                    {JSON.stringify(step.output, null, 2)}
                  </pre>
                </div>
              )}
              {step.error && (
                <div style={{ color: "var(--accent-red)" }}>
                  Error: {step.error}
                </div>
              )}
              <div>Latency: {step.latency_ms}ms</div>
            </details>
          ))}
      </div>
    </div>
  );
}

function DebugEventsSection({ events }: { events: AgentRuntimeEvent[] }) {
  if (!events.length) {
    return <div className="debug-empty">No runtime events</div>;
  }
  return (
    <div className="debug-section">
      <div className="debug-section-title">Runtime Events ({events.length})</div>
      <div className="debug-list">
        {events.map((event, i) => (
          <div key={i} className="debug-list-item">
            <span className="debug-list-seq">{event.sequence}</span>
            <span className="debug-list-type">{event.type}</span>
            <span className="debug-list-time">
              {event.created_at_ms
                ? `${event.created_at_ms}ms`
                : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
