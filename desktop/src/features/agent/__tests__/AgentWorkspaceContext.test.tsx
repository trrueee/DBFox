import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentWorkspace } from "../AgentWorkspace";
import type { AgentArtifact, AgentRunResponse, AgentWorkspaceContext } from "../types";

const workspaceContext: AgentWorkspaceContext = {
  datasource_id: "ds-1",
  project_id: "project-1",
  active_sql: "SELECT id FROM users LIMIT 10",
  last_query_result_preview: { columns: ["id"], rows: [{ id: 1 }], rowCount: 1 },
  selected_table_names: ["users"],
  selected_artifact_id: "artifact-suggestion",
};

const sqlSuggestion: AgentArtifact = {
  id: "artifact-suggestion",
  semantic_id: "sql_suggestion",
  type: "sql_suggestion",
  title: "SQL suggestion",
  payload: {
    proposed_sql: "SELECT id FROM users LIMIT 10",
    suggestions: [
      {
        id: "apply",
        title: "Apply SQL",
        proposed_sql: "SELECT id FROM users LIMIT 10",
        action: "apply_to_editor",
      },
    ],
  },
  presentation: { mode: "both", priority: 1 },
};

const response: AgentRunResponse = {
  run_id: "run-1",
  session_id: "session-1",
  success: true,
  status: "success",
  question: "Explain this SQL",
  artifacts: [sqlSuggestion],
  steps: [],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentWorkspace workspace context", () => {
  it("shows the lightweight workspace context indicator", () => {
    render(<AgentWorkspace result={response} workspaceContext={workspaceContext} />);

    expect(screen.getByText("Current SQL")).toBeTruthy();
    expect(screen.getByText("Last result")).toBeTruthy();
    expect(screen.getByText("Selected table")).toBeTruthy();
    expect(screen.getByText("Selected artifact")).toBeTruthy();
    expect(screen.getByText("users")).toBeTruthy();
  });

  it("applies proposed sql to the editor without executing", () => {
    const onApplySql = vi.fn();
    const onOpenSql = vi.fn();

    render(
      <AgentWorkspace
        result={response}
        workspaceContext={workspaceContext}
        onApplySql={onApplySql}
        onOpenSql={onOpenSql}
      />,
    );

    fireEvent.click(screen.getByText("Apply to SQL Editor"));

    expect(onApplySql).toHaveBeenCalledWith("SELECT id FROM users LIMIT 10");
    expect(onOpenSql).not.toHaveBeenCalled();
  });

  it("passes workspace context through follow-up composer", () => {
    const onAsk = vi.fn();

    render(<AgentWorkspace result={response} workspaceContext={workspaceContext} onAsk={onAsk} />);

    fireEvent.change(screen.getByPlaceholderText("Ask a follow-up about this result"), {
      target: { value: "continue" },
    });
    fireEvent.click(screen.getByText("Ask"));

    expect(onAsk).toHaveBeenCalledWith("continue", workspaceContext);
  });

  it("loads and displays Agent Kernel thread state", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      thread_id: "session-1",
      values: { status: "waiting_approval", step_count: 4 },
      next: ["approval_interrupt"],
      interrupts: [{ id: "interrupt-1", value: { approval_id: "approval-1" } }],
      config: { configurable: { thread_id: "session-1" } },
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AgentWorkspace result={{ ...response, status: "waiting_approval" }} workspaceContext={workspaceContext} />);

    fireEvent.click(screen.getByText("State"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.getByText("waiting_approval")).toBeTruthy();
    expect(screen.getByText("approval_interrupt")).toBeTruthy();
    expect(screen.getByText("1 interrupt")).toBeTruthy();
  });

  it("resets the state inspector when the Agent thread changes", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const isSecondSession = url.includes("session-2");
      return new Response(JSON.stringify({
        thread_id: isSecondSession ? "session-2" : "session-1",
        values: { status: isSecondSession ? "completed" : "waiting_approval", step_count: isSecondSession ? 6 : 4 },
        next: isSecondSession ? [] : ["approval_interrupt"],
        interrupts: [],
        config: { configurable: { thread_id: isSecondSession ? "session-2" : "session-1" } },
      }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<AgentWorkspace result={{ ...response, session_id: "session-1" }} workspaceContext={workspaceContext} />);

    fireEvent.click(screen.getByText("State"));
    await waitFor(() => expect(screen.getByText("waiting_approval")).toBeTruthy());

    rerender(<AgentWorkspace result={{ ...response, session_id: "session-2" }} workspaceContext={workspaceContext} />);

    expect(screen.queryByText("waiting_approval")).toBeNull();
    fireEvent.click(screen.getByText("State"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(screen.getByText("completed")).toBeTruthy();
  });

  it("does not crash when context is absent", () => {
    render(<AgentWorkspace result={response} />);

    expect(screen.getByText("Artifact Inspector")).toBeTruthy();
  });
});
