import { beforeEach, describe, expect, it, vi } from "vitest";
import { getConversation, listConversations } from "../../features/conversation/conversationRepository";
import { agentApi } from "../../lib/api/agent";
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
    streamResumeAgentRun: vi.fn(),
  },
}));

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
  });

  it("stores pending approval details from stream events", () => {
    const store = useConversationStore.getState();
    store.loadConversation({
      id: "conv-approval",
      title: "Approval",
      datasource_id: "ds-1",
      context_tables: [],
      created_at: null,
      updated_at: null,
      messages: [
        {
          id: "assistant-approval",
          conversation_id: "conv-approval",
          role: "assistant",
          content: "",
          status: "streaming",
          sequence: 1,
          created_at: null,
          updated_at: null,
        },
      ],
      runs: [],
      artifacts: [],
      approvals: [],
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
        requested_action: { args: { sql: "SELECT * FROM orders" } },
        created_at: "2026-06-22T00:00:00Z",
      },
    });

    const state = useConversationStore.getState();
    expect(state.runsById["run-approval"].status).toBe("waiting_approval");
    expect(state.runsById["run-approval"].approval?.id).toBe("approval-1");
  });

  it("streams approved approval decisions back into the conversation", async () => {
    const store = useConversationStore.getState();
    store.loadConversation({
      id: "conv-approval",
      title: "Approval",
      datasource_id: "ds-1",
      context_tables: [],
      created_at: null,
      updated_at: null,
      messages: [
        {
          id: "assistant-approval",
          conversation_id: "conv-approval",
          role: "assistant",
          content: "",
          status: "streaming",
          sequence: 1,
          created_at: null,
          updated_at: null,
        },
      ],
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
            requested_action: { args: { sql: "SELECT * FROM orders" } },
            created_at: "2026-06-22T00:00:00Z",
          },
          events: [],
        },
      ],
      artifacts: [],
      approvals: [],
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

    expect(agentApi.streamResumeAgentRun).toHaveBeenCalledWith("run-approval", "approval-1", expect.any(Object));
    const state = useConversationStore.getState();
    expect(state.messagesById["assistant-approval"].content).toBe("已完成");
  });
});
