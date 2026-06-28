import { beforeEach, describe, expect, it, vi } from "vitest";
import { getConversation, listConversations } from "../../features/conversation/conversationRepository";
import { agentApi } from "../../lib/api/agent";
import type { AgentAnswer } from "../../lib/api/types";
import type { ConversationDetail, ConversationMessage, ConversationRun } from "../../types/conversation";
import { useConversationStore } from "../conversationStore";

vi.mock("../../components/SettingsDialog", () => ({
  getStoredApiConfig: () => ({ apiKey: "test-key", apiBase: "", modelName: "test-model" }),
}));

vi.mock("../datasourceStore", () => ({
  useDatasourceStore: {
    getState: () => ({ activeDatasourceId: "ds-1" }),
  },
}));

vi.mock("../../features/conversation/conversationRepository", () => ({
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  getConversation: vi.fn(),
  listConversations: vi.fn(),
  startConversationMessageStream: vi.fn(),
}));

vi.mock("../../lib/api/agent", () => ({
  agentApi: {
    rejectAgentApproval: vi.fn(),
    resolveAgentApproval: vi.fn(),
    streamResumeAgentRun: vi.fn(),
  },
}));

type ConversationStoreState = ReturnType<typeof useConversationStore.getState>;

function answerFixture(answer: string): AgentAnswer {
  return {
    answer,
    key_findings: [],
    evidence: [],
    caveats: [],
    recommendations: [],
    follow_up_questions: [],
  };
}

function assistantMessageFixture(
  conversationId: string,
  id: string,
  overrides: Partial<ConversationMessage> = {},
): ConversationMessage {
  return {
    id,
    conversation_id: conversationId,
    role: "assistant",
    content: "",
    status: "streaming",
    sequence: 1,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function conversationFixture(
  id: string,
  {
    title = "Test",
    messages = [],
    runs = [],
  }: {
    title?: string;
    messages?: ConversationMessage[];
    runs?: ConversationRun[];
  },
): ConversationDetail {
  return {
    id,
    title,
    datasource_id: "ds-1",
    context_tables: [],
    created_at: null,
    updated_at: null,
    messages,
    runs,
    artifacts: [],
    approvals: [],
  };
}

function loadAssistantConversation(
  store: ConversationStoreState,
  {
    conversationId,
    title,
    assistantId,
    runs,
  }: {
    conversationId: string;
    title?: string;
    assistantId: string;
    runs?: ConversationRun[];
  },
) {
  store.loadConversation(
    conversationFixture(conversationId, {
      title,
      messages: [assistantMessageFixture(conversationId, assistantId)],
      runs,
    }),
  );
}

describe("conversationStore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useConversationStore.setState(useConversationStore.getInitialState());
  });

  it("applies assistant delta to the addressed assistant message only", () => {
    const store = useConversationStore.getState();
    store.loadConversation({
      id: "conv-1",
      title: "Test",
      datasource_id: "ds-1",
      context_tables: [],
      created_at: null,
      updated_at: null,
      messages: [
        {
          id: "user-1",
          conversation_id: "conv-1",
          role: "user",
          content: "hello",
          status: "completed",
          sequence: 1,
          created_at: null,
          updated_at: null,
        },
        {
          id: "assistant-1",
          conversation_id: "conv-1",
          role: "assistant",
          content: "",
          status: "streaming",
          sequence: 2,
          created_at: null,
          updated_at: null,
        },
      ],
      runs: [],
      artifacts: [],
      approvals: [],
    });

    store.applyStreamEvent({
      event_id: "event-1",
      run_id: "run-1",
      sequence: 1,
      created_at_ms: 1,
      type: "agent.answer.completed",
      conversation_id: "conv-1",
      message_id: "assistant-1",
      assistant_message_id: "assistant-1",
      answer: {
        answer: "world",
        key_findings: [],
        evidence: [],
        caveats: [],
        recommendations: [],
        follow_up_questions: [],
      },
    });

    const state = useConversationStore.getState();
    expect(state.messagesById["user-1"].content).toBe("hello");
    expect(state.messagesById["assistant-1"].content).toBe("world");
    expect(state.messagesById["assistant-1"].status).toBe("completed");
    expect(state.runsById["run-1"].answer?.answer).toBe("world");
  });

  it("appends answer deltas and reconciles with the completed answer", () => {
    const store = useConversationStore.getState();
    loadAssistantConversation(store, {
      conversationId: "conv-stream",
      title: "Stream",
      assistantId: "assistant-stream",
    });

    store.applyStreamEvent({
      event_id: "delta-1",
      run_id: "run-stream",
      sequence: 1,
      created_at_ms: 1,
      type: "agent.answer.delta",
      conversation_id: "conv-stream",
      message_id: "assistant-stream",
      assistant_message_id: "assistant-stream",
      content: "Hel",
    });
    store.applyStreamEvent({
      event_id: "delta-2",
      run_id: "run-stream",
      sequence: 2,
      created_at_ms: 2,
      type: "agent.answer.delta",
      conversation_id: "conv-stream",
      message_id: "assistant-stream",
      assistant_message_id: "assistant-stream",
      content: "lo",
    });

    let state = useConversationStore.getState();
    expect(state.messagesById["assistant-stream"].content).toBe("Hello");
    expect(state.messagesById["assistant-stream"].status).toBe("streaming");
    expect(state.runsById["run-stream"].answer).toBeNull();

    store.applyStreamEvent({
      event_id: "completed-stream",
      run_id: "run-stream",
      sequence: 3,
      created_at_ms: 3,
      type: "agent.answer.completed",
      conversation_id: "conv-stream",
      message_id: "assistant-stream",
      assistant_message_id: "assistant-stream",
      answer: answerFixture("Hello!"),
    });

    state = useConversationStore.getState();
    expect(state.messagesById["assistant-stream"].content).toBe("Hello!");
    expect(state.messagesById["assistant-stream"].status).toBe("completed");
    expect(state.runsById["run-stream"].answer?.answer).toBe("Hello!");
  });

  it("stores pending approval details from stream events", () => {
    const store = useConversationStore.getState();
    loadAssistantConversation(store, {
      conversationId: "conv-approval",
      title: "Approval",
      assistantId: "assistant-approval",
    });

    store.applyStreamEvent({
      event_id: "event-approval",
      run_id: "run-approval",
      sequence: 1,
      created_at_ms: 1,
      type: "agent.run.waiting_approval",
      conversation_id: "conv-approval",
      assistant_message_id: "assistant-approval",
      approval: {
        id: "approval-1",
        run_id: "run-approval",
        session_id: "conv-approval",
        step_name: "sql.execute_readonly",
        tool_name: "sql.execute_readonly",
        status: "pending",
        risk_level: "warning",
        reason: "生产环境需要确认",
        policy_decision: {},
        requested_action: { args: { safe_sql: "SELECT * FROM orders" } },
        created_at: "2026-06-22T00:00:00Z",
      },
    });

    const state = useConversationStore.getState();
    expect(state.runsById["run-approval"].status).toBe("waiting_approval");
    expect(state.runsById["run-approval"].approval?.id).toBe("approval-1");
  });

  it("streams approved approval decisions back into the conversation", async () => {
    const store = useConversationStore.getState();
    loadAssistantConversation(store, {
      conversationId: "conv-approval",
      title: "Approval",
      assistantId: "assistant-approval",
      runs: [
        {
          id: "run-approval",
          conversation_id: "conv-approval",
          datasource_id: "ds-1",
          question: "orders",
          assistant_message_id: "assistant-approval",
          status: "waiting_approval",
          approval: {
            id: "approval-1",
            run_id: "run-approval",
            session_id: "conv-approval",
            step_name: "sql.execute_readonly",
            tool_name: "sql.execute_readonly",
            status: "pending",
            risk_level: "warning",
            reason: "生产环境需要确认",
            policy_decision: {},
            requested_action: { args: { safe_sql: "SELECT * FROM orders" } },
            created_at: "2026-06-22T00:00:00Z",
          },
          events: [],
        },
      ],
      artifacts: [],
      approvals: [],
    });
    vi.mocked(agentApi.resolveAgentApproval).mockResolvedValue({
      id: "approval-1",
      run_id: "run-approval",
      session_id: "conv-approval",
      step_name: "sql.execute_readonly",
      tool_name: "sql.execute_readonly",
      status: "approved",
      risk_level: "warning",
      reason: "生产环境需要确认",
      policy_decision: {},
      requested_action: { args: { safe_sql: "SELECT * FROM orders" } },
      created_at: "2026-06-22T00:00:00Z",
    });
    vi.mocked(agentApi.streamResumeAgentRun).mockImplementation(async (_runId, _approvalId, options) => {
      options?.onEvent?.({
        event_id: "event-complete",
        run_id: "run-approval",
        sequence: 2,
        created_at_ms: 2,
        type: "agent.answer.completed",
        answer: {
          answer: "已完成",
          key_findings: [],
          evidence: [],
          caveats: [],
          recommendations: [],
          follow_up_questions: [],
        },
      });
      return {
        run_id: "run-approval",
        session_id: "conv-approval",
        success: true,
        status: "completed",
        question: "orders",
        artifacts: [],
        answer: {
          answer: "已完成",
          key_findings: [],
          evidence: [],
          caveats: [],
          recommendations: [],
          follow_up_questions: [],
        },
      };
    });
    vi.mocked(getConversation).mockResolvedValue({
      id: "conv-approval",
      title: "Approval",
      datasource_id: "ds-1",
      context_tables: [],
      created_at: null,
      updated_at: null,
      messages: [{ ...useConversationStore.getState().messagesById["assistant-approval"], content: "已完成", status: "completed" }],
      runs: [{ ...useConversationStore.getState().runsById["run-approval"], status: "completed" }],
      artifacts: [],
      approvals: [],
    });
    vi.mocked(listConversations).mockResolvedValue([]);

    await store.resolveApproval("run-approval", "approval-1", true);

    expect(agentApi.resolveAgentApproval).toHaveBeenCalledWith(
      "run-approval",
      "approval-1",
      "approved",
      "Approved in DBFox UI",
    );
    expect(agentApi.streamResumeAgentRun).toHaveBeenCalledWith("run-approval", "approval-1", expect.any(Object));
    expect(vi.mocked(agentApi.resolveAgentApproval).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(agentApi.streamResumeAgentRun).mock.invocationCallOrder[0],
    );
    const state = useConversationStore.getState();
    expect(state.messagesById["assistant-approval"].content).toBe("已完成");
  });

  it("resolves rejected approval decisions without resuming the run", async () => {
    const store = useConversationStore.getState();
    loadAssistantConversation(store, {
      conversationId: "conv-reject",
      title: "Reject",
      assistantId: "assistant-reject",
      runs: [
        {
          id: "run-reject",
          conversation_id: "conv-reject",
          datasource_id: "ds-1",
          question: "orders",
          assistant_message_id: "assistant-reject",
          status: "waiting_approval",
          approval: {
            id: "approval-reject",
            run_id: "run-reject",
            session_id: "conv-reject",
            step_name: "sql.execute_readonly",
            tool_name: "sql.execute_readonly",
            status: "pending",
            risk_level: "warning",
            reason: "生产环境需要确认",
            policy_decision: {},
            requested_action: { args: { safe_sql: "SELECT * FROM orders" } },
            created_at: "2026-06-22T00:00:00Z",
          },
          events: [],
        },
      ],
    });
    const rejectedApproval = {
      id: "approval-reject",
      run_id: "run-reject",
      session_id: "conv-reject",
      step_name: "sql.execute_readonly",
      tool_name: "sql.execute_readonly",
      status: "rejected" as const,
      risk_level: "warning",
      reason: "生产环境需要确认",
      policy_decision: {},
      requested_action: { args: { safe_sql: "SELECT * FROM orders" } },
      created_at: "2026-06-22T00:00:00Z",
    };
    vi.mocked(agentApi.resolveAgentApproval).mockResolvedValue(rejectedApproval);
    vi.mocked(agentApi.rejectAgentApproval).mockResolvedValue({
      run_id: "run-reject",
      session_id: "conv-reject",
      success: false,
      status: "failed",
      question: "orders",
      artifacts: [],
      approval: rejectedApproval,
    });

    await store.resolveApproval("run-reject", "approval-reject", false);

    expect(agentApi.resolveAgentApproval).toHaveBeenCalledWith(
      "run-reject",
      "approval-reject",
      "rejected",
      "Rejected in DBFox UI",
    );
    expect(agentApi.streamResumeAgentRun).not.toHaveBeenCalled();
    expect(agentApi.rejectAgentApproval).not.toHaveBeenCalled();
    expect(useConversationStore.getState().runsById["run-reject"].approval?.status).toBe("rejected");
    expect(useConversationStore.getState().messagesById["assistant-reject"].status).toBe("failed");
  });

  it("does not replace a run when a duplicate event is ignored", () => {
    const store = useConversationStore.getState();
    loadAssistantConversation(store, {
      conversationId: "conv-events",
      title: "Events",
      assistantId: "assistant-events",
    });
    const event = {
      event_id: "event-same",
      run_id: "run-events",
      sequence: 1,
      created_at_ms: 1,
      type: "agent.progress.update",
      conversation_id: "conv-events",
      assistant_message_id: "assistant-events",
      step: { phase: "understanding", status: "running", summary: "理解问题" },
    } as const;

    store.applyStreamEvent(event);
    const firstRun = useConversationStore.getState().runsById["run-events"];
    store.applyStreamEvent(event);

    expect(useConversationStore.getState().runsById["run-events"]).toBe(firstRun);
  });

  it("applies a batch of stream events in order", () => {
    const store = useConversationStore.getState();
    loadAssistantConversation(store, {
      conversationId: "conv-batch",
      title: "Batch",
      assistantId: "assistant-batch",
    });

    store.applyStreamEvents([
      {
        event_id: "event-1",
        run_id: "run-batch",
        sequence: 1,
        created_at_ms: 1,
        type: "agent.progress.update",
        conversation_id: "conv-batch",
        assistant_message_id: "assistant-batch",
        step: { phase: "understanding", status: "running", summary: "理解问题" },
      },
      {
        event_id: "event-2",
        run_id: "run-batch",
        sequence: 2,
        created_at_ms: 2,
        type: "agent.answer.completed",
        conversation_id: "conv-batch",
        assistant_message_id: "assistant-batch",
        message_id: "assistant-batch",
        answer: {
          answer: "完成",
          key_findings: [],
          evidence: [],
          caveats: [],
          recommendations: [],
          follow_up_questions: [],
        },
      },
    ]);

    const state = useConversationStore.getState();
    expect(state.runsById["run-batch"].events).toHaveLength(2);
    expect(state.messagesById["assistant-batch"].content).toBe("完成");
  });
});
