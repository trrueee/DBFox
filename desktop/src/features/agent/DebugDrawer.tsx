import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "../../components/ui/button";
import type {
  AgentRunResponse, AgentRuntimeEvent, AgentStep, AgentTraceEvent, AgentWorkspaceContext,
} from "../../lib/api";

interface DebugDrawerProps {
  open: boolean; onClose: () => void;
  workspaceContext?: AgentWorkspaceContext | null;
  response?: AgentRunResponse | null;
  steps?: AgentStep[];
  traceEvents?: AgentTraceEvent[];
  runtimeEvents?: AgentRuntimeEvent[];
}

type DebugTab = "state" | "trace" | "tools" | "policy" | "events" | "raw";

const TABS: { key: DebugTab; label: string }[] = [
  { key: "state", label: "State" }, { key: "trace", label: "Trace" },
  { key: "tools", label: "Tool calls" }, { key: "policy", label: "Policy" },
  { key: "events", label: "Events" }, { key: "raw", label: "Raw response" },
];

export function DebugDrawer({ open, onClose, workspaceContext, response, steps, traceEvents, runtimeEvents }: DebugDrawerProps) {
  const [tab, setTab] = useState<DebugTab>("state");
  if (!open) return null;

  return (
    <div className="border-t border-[hsl(var(--border))] bg-[hsl(var(--card))] max-h-[280px] flex flex-col shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 bg-[hsl(var(--secondary))] border-b border-[hsl(var(--border))]">
        <span className="text-[0.66rem] font-semibold text-[hsl(var(--muted-foreground))]">Debug Panel</span>
        <Button variant="ghost" size="icon-sm" onClick={onClose}><X size={12} /></Button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[hsl(var(--border))] bg-[hsl(var(--secondary))]">
        {TABS.map((t) => (
          <button key={t.key} type="button"
            className={`px-2 py-0.5 text-[0.62rem] border-b-2 transition-colors font-sans cursor-pointer border-none bg-transparent ${
              tab === t.key
                ? "text-[hsl(var(--primary))] border-[hsl(var(--primary))] font-semibold"
                : "text-[hsl(var(--muted-foreground))] border-transparent hover:text-[hsl(var(--foreground))]"
            }`}
            onClick={() => setTab(t.key)}
          >{t.label}</button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-2">
        {tab === "state" && <JsonSection title="WorkspaceContext" data={workspaceContext} />}
        {tab === "trace" && <TraceSection events={traceEvents || []} />}
        {tab === "tools" && <ToolsSection steps={steps || []} />}
        {tab === "policy" && <JsonSection title="Policy Decision"
          data={response?.approval?.policy_decision || steps?.find(s => s.name === "validate_sql")} />}
        {tab === "events" && <EventsSection events={runtimeEvents || []} />}
        {tab === "raw" && <JsonSection title="AgentRunResponse" data={response} />}
      </div>
    </div>
  );
}

function JsonSection({ title, data }: { title: string; data?: unknown }) {
  return (
    <div className="mb-2">
      <div className="text-[0.64rem] font-semibold text-[hsl(var(--muted-foreground))] mb-1">{title}</div>
      <pre className="font-mono text-[0.62rem] leading-relaxed bg-[hsl(var(--secondary))] p-1.5 rounded overflow-x-auto max-h-[160px] overflow-y-auto whitespace-pre text-[hsl(var(--foreground))]">
        {data ? JSON.stringify(data, null, 2) : "(empty)"}
      </pre>
    </div>
  );
}

function TraceSection({ events }: { events: AgentTraceEvent[] }) {
  if (!events.length) return <div className="text-[0.64rem] text-[hsl(var(--muted-foreground))] p-2.5 text-center">No trace events</div>;
  return (
    <div className="mb-2">
      <div className="text-[0.64rem] font-semibold text-[hsl(var(--muted-foreground))] mb-1">Trace Events ({events.length})</div>
      <div className="flex flex-col gap-0.5">
        {events.map((event, i) => (
          <div key={i} className="flex items-center gap-2 text-[0.64rem] py-0.5 px-1">
            <span className="text-[hsl(var(--primary))] font-medium font-mono text-[0.62rem]">{event.type}</span>
            <span className="text-[hsl(var(--muted-foreground))]">{typeof event.step?.name === "string" ? event.step.name : "-"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ToolsSection({ steps }: { steps: AgentStep[] }) {
  return (
    <div className="mb-2">
      <div className="text-[0.64rem] font-semibold text-[hsl(var(--muted-foreground))] mb-1">Tool Calls</div>
      <div className="flex flex-col gap-0.5">
        {steps.filter(s => s.input || s.output).map((step, i) => (
          <details key={i} className="text-[0.64rem]">
            <summary className="cursor-pointer py-0.5 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]">
              {step.name} — {step.status}
            </summary>
            {step.input && <div className="mt-1"><strong>Input:</strong><pre className="font-mono text-[0.6rem] bg-[hsl(var(--secondary))] p-1 rounded mt-0.5 overflow-x-auto whitespace-pre text-[hsl(var(--foreground))]">{JSON.stringify(step.input, null, 2)}</pre></div>}
            {step.output && <div className="mt-1"><strong>Output:</strong><pre className="font-mono text-[0.6rem] bg-[hsl(var(--secondary))] p-1 rounded mt-0.5 overflow-x-auto whitespace-pre text-[hsl(var(--foreground))]">{JSON.stringify(step.output, null, 2)}</pre></div>}
            {step.error && <div className="text-[hsl(var(--destructive))] mt-1">Error: {step.error}</div>}
            <div className="mt-0.5">Latency: {step.latency_ms}ms</div>
          </details>
        ))}
      </div>
    </div>
  );
}

function EventsSection({ events }: { events: AgentRuntimeEvent[] }) {
  if (!events.length) return <div className="text-[0.64rem] text-[hsl(var(--muted-foreground))] p-2.5 text-center">No runtime events</div>;
  return (
    <div className="mb-2">
      <div className="text-[0.64rem] font-semibold text-[hsl(var(--muted-foreground))] mb-1">Runtime Events ({events.length})</div>
      <div className="flex flex-col gap-0.5">
        {events.map((event, i) => (
          <div key={i} className="flex items-center gap-2 text-[0.64rem] py-0.5 px-1">
            <span className="w-6 text-[hsl(var(--muted-foreground))] font-mono">{event.sequence}</span>
            <span className="text-[hsl(var(--primary))] font-medium font-mono text-[0.62rem]">{event.type}</span>
            <span className="ml-auto text-[hsl(var(--muted-foreground))] font-mono">{event.created_at_ms ? `${event.created_at_ms}ms` : ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
