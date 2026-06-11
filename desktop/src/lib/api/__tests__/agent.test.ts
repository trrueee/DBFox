import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createAgentRunDraft,
  agentApi,
  reduceAgentRuntimeEvent,
  rejectAgentApproval,
  streamResumeAgentRun,
} from "../agent";
import type { AgentApproval, AgentArtifact, AgentRunResponse, AgentRuntimeEvent } from "../types";

const approval: AgentApproval = {
  id: "approval_1",
  run_id: "run_1",
  session_id: "session_1",
  step_name: "validate_sql",
  tool_name: "sql.execute_readonly",
  status: "pending",
  risk_level: "warning",
  reason: "Production datasource requires confirmation.",
  policy_decision: { blocked_reasons: ["requires_confirmation"] },
  requested_action: { sql: "SELECT id FROM users LIMIT 3" },
  created_at: "2026-06-02T00:00:00Z",
};

const completedResponse: AgentRunResponse = {
  run_id: "run_1",
  session_id: "session_1",
  success: true,
  status: "success",
  question: "list users",
  steps: [],
  artifacts: [],
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("agent runtime reducer", () => {
  it("stores approval state and marks waiting_approval without failing", () => {
    let draft = createAgentRunDraft("list users");
    draft = reduceAgentRuntimeEvent(draft, event("agent.approval.required", { approval }));
    draft = reduceAgentRuntimeEvent(draft, event("agent.run.waiting_approval", {
      approval,
      response: {
        ...completedResponse,
        success: false,
        status: "waiting_approval",
        approval,
      },
    }));

    expect(draft.status).toBe("waiting_approval");
    expect(draft.error).toBeNull();
    expect(draft.approval?.id).toBe("approval_1");
    expect(draft.response?.status).toBe("waiting_approval");
  });

  it("keeps old completed events working", () => {
    const draft = reduceAgentRuntimeEvent(createAgentRunDraft("list users"), event("agent.run.completed", {
      response: completedResponse,
    }));

    expect(draft.status).toBe("completed");
    expect(draft.response?.run_id).toBe("run_1");
  });

  it("replaces streamed plan artifacts by semantic id", () => {
    const firstPlan = planArtifact("artifact-plan-1", "pending");
    const updatedPlan = planArtifact("artifact-plan-2", "completed");
    let draft = createAgentRunDraft("list users");

    draft = reduceAgentRuntimeEvent(draft, event("agent.artifact.created", { artifact: firstPlan }));
    draft = reduceAgentRuntimeEvent(draft, event("agent.artifact.created", { artifact: updatedPlan }));

    expect(draft.artifacts).toHaveLength(1);
    expect(draft.artifacts[0].id).toBe("artifact-plan-2");
    expect((draft.artifacts[0].payload.steps as Array<Record<string, unknown>>)[0].status).toBe("completed");
  });

  it("keeps a new pending approval when an old approval resolves later", () => {
    const newApproval: AgentApproval = {
      ...approval,
      id: "approval_2",
      run_id: "run_2",
      requested_action: { sql: "SELECT id FROM users LIMIT 10" },
    };
    const oldExpired: AgentApproval = {
      ...approval,
      status: "expired",
      decision_note: "Superseded by user SQL revision before approval.",
    };
    let draft = createAgentRunDraft("change limit");

    draft = reduceAgentRuntimeEvent(draft, event("agent.approval.required", { approval: newApproval, run_id: "run_2" }));
    draft = reduceAgentRuntimeEvent(draft, event("agent.approval.resolved", { approval: oldExpired }));

    expect(draft.approval?.id).toBe("approval_2");
    expect(draft.approval?.status).toBe("pending");
    expect(draft.error).toBeNull();
  });
});

describe("agent approval api", () => {
  it("sends workspace_context with agent run payloads", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(completedResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await agentApi.runAgentQuery("ds-1", "Explain this SQL", {
      workspaceContext: {
        datasource_id: "ds-1",
        active_sql: "SELECT id FROM users LIMIT 10",
        selected_table_names: ["users"],
      },
    });

    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(String(options?.body));
    expect(body.workspace_context).toEqual({
      datasource_id: "ds-1",
      active_sql: "SELECT id FROM users LIMIT 10",
      selected_table_names: ["users"],
    });
  });

  it("runs agent queries through the Agent Kernel endpoint", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(completedResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await agentApi.runAgentQuery("ds-1", "list users");

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/agent/run");
  });

  it("loads Agent Kernel thread state for the state inspector", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      thread_id: "session_1",
      values: { status: "waiting_approval", step_count: 4 },
      next: ["approval_interrupt"],
      interrupts: [{ id: "interrupt_1", value: { approval_id: "approval_1" } }],
      config: { configurable: { thread_id: "session_1" } },
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const state = await agentApi.getAgentThreadState("session_1");

    expect(state.thread_id).toBe("session_1");
    expect(state.values?.status).toBe("waiting_approval");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/agent/runs/session_1");
  });

  it("posts rejection decisions to the Agent Kernel endpoint", async () => {
    const rejectedResponse: AgentRunResponse = {
      ...completedResponse,
      success: false,
      status: "failed",
      approval: { ...approval, status: "rejected" },
    };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(rejectedResponse), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await rejectAgentApproval("run_1", "approval_1", "reviewed");

    expect(result.approval?.status).toBe("rejected");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/agent/runs");
    expect(JSON.parse(String(options?.body))).toEqual({ run_id: "run_1", approval_id: "approval_1", approved: false, note: "reviewed" });
  });

  it("streams resume events and returns the final response", async () => {
    const resumed = event("agent.run.resumed", { approval: { ...approval, status: "approved" } });
    const completed = event("agent.run.completed", { response: completedResponse });
    const body = `event: agent.run.resumed\ndata: ${JSON.stringify(resumed)}\n\nevent: agent.run.completed\ndata: ${JSON.stringify(completed)}\n\n`;
    const fetchMock = vi.fn(async () => new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const onEvent = vi.fn();

    const result = await streamResumeAgentRun("run_1", "approval_1", { onEvent });

    expect(result.run_id).toBe("run_1");
    expect(onEvent).toHaveBeenCalledTimes(2);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/agent/runs");
    expect(JSON.parse(String(options?.body))).toEqual({
      run_id: "run_1",
      approval_id: "approval_1",
      approved: true,
      note: null,
    });
  });

  it("skips malformed SSE events and continues to the final response", async () => {
    const completed = event("agent.run.completed", { response: completedResponse });
    const body = `event: agent.noisy\ndata: {not-json}\n\nevent: agent.run.completed\ndata: ${JSON.stringify(completed)}\n\n`;
    const fetchMock = vi.fn(async () => new Response(body, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const onEvent = vi.fn();

    const result = await streamResumeAgentRun("run_1", "approval_1", { onEvent });

    expect(result.run_id).toBe("run_1");
    expect(onEvent).toHaveBeenCalledTimes(1);
  });
});

function event(type: AgentRuntimeEvent["type"], patch: Partial<AgentRuntimeEvent>): AgentRuntimeEvent {
  return {
    event_id: `${type}_1`,
    run_id: "run_1",
    sequence: 1,
    created_at_ms: 1,
    type,
    ...patch,
  };
}

function planArtifact(id: string, status: string): AgentArtifact {
  return {
    id,
    semantic_id: "agent_plan_draft",
    type: "agent_plan",
    title: "Agent plan",
    payload: {
      version: "agent-plan/v1",
      steps: [{ id: "schema", title: "Inspect schema", status, tool_name: "schema.build_context" }],
    },
    presentation: { mode: "dock", priority: 90 },
  };
}
