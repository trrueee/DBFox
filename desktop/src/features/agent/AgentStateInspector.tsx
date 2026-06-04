import { useState } from "react";
import { api, type AgentKernelThreadState } from "../../lib/api";

interface AgentStateInspectorProps {
  threadId?: string | null;
}

export function AgentStateInspector({ threadId }: AgentStateInspectorProps) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<AgentKernelThreadState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!threadId) return null;

  const loadState = async () => {
    setLoading(true);
    setError(null);
    try {
      setState(await api.getAgentThreadState(threadId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load state.");
    } finally {
      setLoading(false);
    }
  };

  const toggle = () => {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (nextOpen && !state && !loading) {
      void loadState();
    }
  };

  return (
    <section style={{ padding: 8, background: "var(--bg-secondary)" }}>
      <button
        className="btn-ghost"
        onClick={toggle}
        style={{ width: "100%", justifyContent: "space-between", fontSize: "0.66rem" }}
      >
        <span>State</span>
        <span>{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <span style={{ color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {threadId}
            </span>
            <button className="btn-secondary" type="button" onClick={() => void loadState()} disabled={loading} style={{ fontSize: "0.62rem", padding: "2px 7px" }}>
              Refresh
            </button>
          </div>
          {loading ? <div style={{ color: "var(--text-muted)" }}>Loading state</div> : null}
          {error ? <div style={{ color: "var(--accent-red)" }}>{error}</div> : null}
          {state ? <ThreadStateSummary state={state} /> : null}
        </div>
      ) : null}
    </section>
  );
}

function ThreadStateSummary({ state }: { state: AgentKernelThreadState }) {
  const values = state.values || {};
  const status = typeof values.status === "string" ? values.status : "unknown";
  const stepCount = typeof values.step_count === "number" ? String(values.step_count) : "-";
  const next = state.next?.length ? state.next.join(", ") : "none";
  const interruptCount = state.interrupts?.length || 0;

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 5 }}>
        <StateChip label="Status" value={status} />
        <StateChip label="Steps" value={stepCount} />
        <StateChip label="Next" value={next} />
        <StateChip label="Interrupts" value={`${interruptCount} ${interruptCount === 1 ? "interrupt" : "interrupts"}`} />
      </div>
      <details>
        <summary style={{ cursor: "pointer", color: "var(--text-secondary)" }}>JSON</summary>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "0.62rem", overflowX: "auto", background: "#fff", padding: 6 }}>
          {JSON.stringify(state, null, 2)}
        </pre>
      </details>
    </>
  );
}

function StateChip({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ color: "var(--text-muted)", fontSize: "0.58rem", fontWeight: 700 }}>{label}</div>
      <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={value}>
        {value}
      </div>
    </div>
  );
}
