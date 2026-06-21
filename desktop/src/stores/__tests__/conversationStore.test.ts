import { beforeEach, describe, expect, it, vi } from "vitest";
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

describe("conversationStore", () => {
  beforeEach(() => {
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
});
