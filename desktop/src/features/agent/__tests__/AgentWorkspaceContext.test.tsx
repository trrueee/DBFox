import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentWorkspace } from "../AgentWorkspace";
import type { AgentApproval, AgentArtifact, AgentRunDraftState, AgentRunResponse, AgentRuntimeEvent, AgentWorkspaceContext } from "../types";

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

const agentPlan: AgentArtifact = {
  id: "artifact-plan",
  semantic_id: "agent_plan_draft",
  type: "agent_plan",
  title: "Agent plan draft",
  payload: {
    version: "agent-plan/v1",
    steps: [
      {
        id: "schema",
        title: "Inspect schema",
        status: "completed",
        tool_name: "schema.build_context",
        depends_on: [],
      },
      {
        id: "answer",
        title: "Answer from evidence",
        status: "pending",
        tool_name: "answer.synthesize",
        depends_on: ["schema"],
      },
    ],
  },
  presentation: { mode: "dock", priority: 90 },
};

const sqlArtifact: AgentArtifact = {
  id: "artifact-sql",
  semantic_id: "sql_candidate",
  type: "sql",
  title: "Validated SQL",
  payload: {
    sql: "SELECT id FROM users LIMIT 5",
    safety_state: { available: true, can_execute: true, requires_confirmation: false },
  },
  presentation: { mode: "dock", priority: 70 },
};

const safetyArtifact: AgentArtifact = {
  id: "artifact-safety",
  semantic_id: "safety_report",
  type: "safety",
  title: "Safety report",
  payload: {
    passed: true,
    can_execute: true,
    requires_confirmation: true,
    blocked_reasons: ["requires_confirmation"],
    messages: ["Production datasource requires manual confirmation."],
    safe_sql: "SELECT id FROM users LIMIT 5",
  },
  presentation: { mode: "dock", priority: 75 },
};

const tableArtifact: AgentArtifact = {
  id: "artifact-table",
  semantic_id: "result_table",
  type: "table",
  title: "Result table",
  payload: {
    columns: ["id", "username"],
    rows: [{ id: 1, username: "alice" }],
    rowCount: 1,
    safety_state: { available: true, can_execute: true, requires_confirmation: false },
  },
  presentation: { mode: "both", priority: 20 },
};

const recommendationArtifact: AgentArtifact = {
  id: "artifact-recommendation",
  semantic_id: "recommendations",
  type: "recommendation",
  title: "Recommended next steps",
  payload: {
    recommendations: ["Compare the same metric by region."],
    followUpQuestions: ["Show this by region"],
  },
  presentation: { mode: "inline", priority: 40 },
};

const response: AgentRunResponse = {
  run_id: "run-1",
  session_id: "session-1",
  success: true,
  status: "success",
  question: "Explain this SQL",
  sql: "SELECT id FROM users LIMIT 5",
  artifacts: [sqlSuggestion],
  steps: [],
};

const pendingApproval: AgentApproval = {
  id: "approval-1",
  run_id: "run-1",
  session_id: "session-1",
  step_name: "execute_sql",
  tool_name: "sql.execute_readonly",
  status: "pending",
  risk_level: "warning",
  reason: "Production datasource requires manual confirmation.",
  policy_decision: {
    messages: ["Production datasource requires manual confirmation."],
    blocked_reasons: ["requires_confirmation"],
  },
  requested_action: {
    tool_name: "sql.execute_readonly",
    args: {
      safe_sql: "SELECT id FROM users LIMIT 3",
    },
  },
  created_at: "2026-06-02T00:00:00Z",
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

  it("offers SQL artifact actions without executing", () => {
    const onApplySql = vi.fn();
    const onOpenSql = vi.fn();
    const onAsk = vi.fn();

    render(
      <AgentWorkspace
        result={{ ...response, artifacts: [sqlArtifact] }}
        workspaceContext={workspaceContext}
        onApplySql={onApplySql}
        onOpenSql={onOpenSql}
        onAsk={onAsk}
      />,
    );

    fireEvent.click(screen.getByText("Open SQL"));
    expect(onOpenSql).toHaveBeenCalledWith("SELECT id FROM users LIMIT 5");

    fireEvent.click(screen.getByText("Apply to SQL Editor"));
    expect(onApplySql).toHaveBeenCalledWith("SELECT id FROM users LIMIT 5");

    fireEvent.click(screen.getByText("Explain SQL"));
    fireEvent.click(screen.getByText("Revise SQL"));

    expect(onAsk).toHaveBeenNthCalledWith(
      1,
      "Explain this SQL",
      expect.objectContaining({
        selected_artifact_id: "artifact-sql",
        selected_sql: "SELECT id FROM users LIMIT 5",
        active_sql: "SELECT id FROM users LIMIT 5",
      }),
    );
    expect(onAsk).toHaveBeenNthCalledWith(
      2,
      "Revise this SQL",
      expect.objectContaining({
        selected_artifact_id: "artifact-sql",
        selected_sql: "SELECT id FROM users LIMIT 5",
        active_sql: "SELECT id FROM users LIMIT 5",
      }),
    );
  });

  it("passes workspace context through follow-up composer", () => {
    const onAsk = vi.fn();

    render(<AgentWorkspace result={response} workspaceContext={workspaceContext} onAsk={onAsk} />);

    fireEvent.change(screen.getByPlaceholderText("Ask a follow-up about this result"), {
      target: { value: "continue" },
    });
    // New Composer uses a Send icon button instead of "Ask" text
    const submitBtn = document.querySelector('button[type="submit"]');
    expect(submitBtn).not.toBeNull();
    fireEvent.click(submitBtn!);

    expect(onAsk).toHaveBeenCalledWith("continue", workspaceContext);
  });

  it("allows approval follow-up questions with approval-aware workspace context", () => {
    const onAsk = vi.fn();

    render(
      <AgentWorkspace
        result={{ ...response, success: false, status: "waiting_approval", approval: pendingApproval }}
        workspaceContext={workspaceContext}
        onAsk={onAsk}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Ask about this pending approval, SQL, or risk"), {
      target: { value: "Why does this need approval?" },
    });
    // New Composer uses a Send icon button instead of "Ask" text
    const submitBtn = document.querySelector('button[type="submit"]');
    expect(submitBtn).not.toBeNull();
    fireEvent.click(submitBtn!);

    expect(onAsk).toHaveBeenCalledWith(
      "Why does this need approval?",
      expect.objectContaining({
        datasource_id: "ds-1",
        pending_approval_id: "approval-1",
        pending_approval_status: "pending",
        pending_approval_reason: "Production datasource requires manual confirmation.",
        selected_sql: "SELECT id FROM users LIMIT 3",
        active_sql: "SELECT id FROM users LIMIT 3",
        selected_artifact_id: "artifact-suggestion",
      }),
    );
  });

  it("shows a compact step timeline for completed Agent runs", () => {
    render(
      <AgentWorkspace
        result={{
          ...response,
          steps: [
            { name: "build_schema_context", status: "success", latency_ms: 12 },
            { name: "validate_sql", status: "failed", error: "invalid sql", latency_ms: 3 },
            { name: "execute_sql", status: "skipped", latency_ms: 0 },
          ],
        }}
        workspaceContext={workspaceContext}
      />,
    );

    expect(screen.getByText("Step timeline")).toBeTruthy();
    expect(screen.getByText("build_schema_context")).toBeTruthy();
    expect(screen.getByText("validate_sql")).toBeTruthy();
    expect(screen.getByText("failed")).toBeTruthy();
    expect(screen.getByText("execute_sql")).toBeTruthy();
    expect(screen.getByText("skipped")).toBeTruthy();
  });

  it("shows agent plan artifacts as a read-only checklist", () => {
    render(
      <AgentWorkspace
        result={{ ...response, artifacts: [agentPlan] }}
        workspaceContext={workspaceContext}
      />,
    );

    expect(screen.getByText("Plan checklist")).toBeTruthy();
    expect(screen.getByText("Inspect schema")).toBeTruthy();
    expect(screen.getByText("Answer from evidence")).toBeTruthy();
    expect(screen.getByText("schema.build_context")).toBeTruthy();
    expect(screen.getByText("depends on schema")).toBeTruthy();
  });

  it("shows safety artifacts with SQL, blocked reasons, and messages", () => {
    render(
      <AgentWorkspace
        result={{ ...response, artifacts: [safetyArtifact] }}
        workspaceContext={workspaceContext}
      />,
    );

    expect(screen.getAllByText("Safety report").length).toBeGreaterThan(0);
    expect(screen.getByText("Can execute")).toBeTruthy();
    expect(screen.getByText("Requires confirmation")).toBeTruthy();
    expect(screen.getByText("Blocked reasons")).toBeTruthy();
    expect(screen.getByText("requires_confirmation")).toBeTruthy();
    expect(screen.getByText("Messages")).toBeTruthy();
    expect(screen.getByText("Production datasource requires manual confirmation.")).toBeTruthy();
    expect(screen.getByText("Safe SQL")).toBeTruthy();
    expect(screen.getByText("SELECT id FROM users LIMIT 5")).toBeTruthy();
  });

  it("shows table artifacts in the inspector", () => {
    render(
      <AgentWorkspace
        result={{ ...response, artifacts: [tableArtifact] }}
        workspaceContext={workspaceContext}
      />,
    );

    expect(screen.getAllByText("Result table").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1 rows").length).toBeGreaterThan(0);
    expect(screen.getAllByText("id").length).toBeGreaterThan(0);
    expect(screen.getAllByText("username").length).toBeGreaterThan(0);
    expect(screen.getAllByText("alice").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Safety: executable").length).toBeGreaterThan(0);
  });

  it("shows recommendation artifacts and asks follow-up questions with artifact context", () => {
    const onAsk = vi.fn();

    render(
      <AgentWorkspace
        result={{ ...response, artifacts: [recommendationArtifact] }}
        workspaceContext={workspaceContext}
        onAsk={onAsk}
      />,
    );

    expect(screen.getAllByText("Recommended next steps").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Compare the same metric by region.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Show this by region").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByLabelText("Ask follow-up: Show this by region"));

    expect(onAsk).toHaveBeenCalledWith(
      "Show this by region",
      expect.objectContaining({ selected_artifact_id: "artifact-recommendation" }),
    );
  });

  it("shows an empty recommendation artifact state", () => {
    render(
      <AgentWorkspace
        result={{
          ...response,
          artifacts: [
            {
              ...recommendationArtifact,
              payload: { recommendations: [], followUpQuestions: [] },
            },
          ],
        }}
        workspaceContext={workspaceContext}
      />,
    );

    expect(screen.getAllByText("No recommendations yet.").length).toBeGreaterThan(0);
  });

  it("shows running steps from streamed draft events", () => {
    const draft: AgentRunDraftState = {
      status: "running",
      question: "list users",
      events: [
        runtimeEvent("agent.step.started", 1, { step: { name: "build_schema_context" } }),
        runtimeEvent("agent.step.completed", 2, { step: { name: "build_schema_context", status: "success", latency_ms: 12 } }),
        runtimeEvent("agent.step.started", 3, { step: { name: "validate_sql" } }),
      ],
      artifacts: [],
      answer: null,
      response: null,
      approval: null,
      checkpoint: null,
      error: null,
    };

    render(<AgentWorkspace draft={draft} workspaceContext={workspaceContext} />);

    expect(screen.getByText("build_schema_context")).toBeTruthy();
    expect(screen.getByText("validate_sql")).toBeTruthy();
    expect(screen.getByText("running")).toBeTruthy();
  });

  it("does not crash when context is absent", () => {
    render(<AgentWorkspace result={response} />);

    expect(screen.getByText("Artifact Inspector")).toBeTruthy();
  });
});

function runtimeEvent(type: AgentRuntimeEvent["type"], sequence: number, patch: Partial<AgentRuntimeEvent>): AgentRuntimeEvent {
  return {
    event_id: `${type}_${sequence}`,
    run_id: "run-1",
    sequence,
    created_at_ms: sequence,
    type,
    ...patch,
  };
}
