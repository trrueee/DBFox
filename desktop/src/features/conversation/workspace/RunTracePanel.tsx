import type { ConversationRun } from "../../../types/conversation";

export function RunTracePanel({ run }: { run: ConversationRun }) {
  return (
    <details className="conv-run-trace">
      <summary>{run.status === "running" ? "Analyzing..." : `Run ${run.status}`}</summary>
      <div className="conv-run-trace-body">
        <div>Run ID: {run.id}</div>
        {run.error_message && <div>{run.error_message}</div>}
      </div>
    </details>
  );
}
