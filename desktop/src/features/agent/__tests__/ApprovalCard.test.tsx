import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../lib/api";
import { ApprovalCard } from "../ApprovalCard";
import type { AgentApproval, AgentRunResponse } from "../types";

vi.mock("../../../lib/api", () => ({
  api: {
    rejectAgentApproval: vi.fn(),
    streamResumeAgentRun: vi.fn(),
  },
}));

const pendingApproval: AgentApproval = {
  id: "approval_1",
  run_id: "run_1",
  session_id: "session_1",
  step_name: "validate_sql",
  tool_name: "sql.execute_readonly",
  status: "pending",
  risk_level: "warning",
  reason: "Production datasource requires manual confirmation.",
  policy_decision: {
    messages: ["Production datasource requires manual confirmation."],
    blocked_reasons: ["requires_confirmation"],
  },
  requested_action: {
    sql: "SELECT id FROM users LIMIT 3",
  },
  created_at: "2026-06-02T00:00:00Z",
};

const finalResponse: AgentRunResponse = {
  run_id: "run_1",
  session_id: "session_1",
  success: true,
  status: "success",
  question: "list users",
  steps: [],
  artifacts: [],
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("ApprovalCard", () => {
  it("shows approval details and resumes after approve", async () => {
    vi.mocked(api.streamResumeAgentRun).mockImplementation(async (_runId, _approvalId, options) => {
      options?.onEvent?.({
        event_id: "resume_1",
        run_id: "run_1",
        sequence: 1,
        created_at_ms: 1,
        type: "agent.run.resumed",
        approval: { ...pendingApproval, status: "approved" },
      });
      return finalResponse;
    });
    const onRuntimeEvent = vi.fn();
    const onResumeComplete = vi.fn();

    render(
      <ApprovalCard
        approval={pendingApproval}
        onRuntimeEvent={onRuntimeEvent}
        onResumeComplete={onResumeComplete}
      />,
    );

    expect(screen.getByText("Approval required")).toBeTruthy();
    expect(screen.getByText("requires_confirmation")).toBeTruthy();

    fireEvent.click(screen.getByText("Approve execute"));

    await waitFor(() => expect(api.streamResumeAgentRun).toHaveBeenCalledWith(
      "run_1",
      "approval_1",
      expect.objectContaining({ note: "Reviewed in DataBox Agent UI." }),
    ));
    expect(onRuntimeEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "agent.run.resumed" }));
    expect(onResumeComplete).toHaveBeenCalledWith(finalResponse);
  });

  it("rejects without starting resume", async () => {
    vi.mocked(api.rejectAgentApproval).mockResolvedValue({
      ...finalResponse,
      success: false,
      status: "failed",
      approval: { ...pendingApproval, status: "rejected" },
    });

    render(<ApprovalCard approval={pendingApproval} />);

    fireEvent.click(screen.getByText("Reject"));

    await waitFor(() => expect(api.rejectAgentApproval).toHaveBeenCalledWith(
      "run_1",
      "approval_1",
      "Rejected in DataBox Agent UI.",
    ));
    expect(api.streamResumeAgentRun).not.toHaveBeenCalled();
    expect(await screen.findByText("Approval rejected.")).toBeTruthy();
  });
});
