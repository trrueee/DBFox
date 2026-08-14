import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact, ConversationDetail } from "../../types/conversation";

const mocks = vi.hoisted(() => ({
  admit: vi.fn(),
  create: vi.fn(),
  getRunArtifacts: vi.fn(),
  follow: vi.fn(),
}));

vi.mock("../../features/conversation/conversationRepository", () => ({
  admitConversationInput: mocks.admit,
  cancelConversationRun: vi.fn(),
  createConversation: mocks.create,
  deleteConversation: vi.fn(),
  getConversation: vi.fn(),
  getConversationHistory: vi.fn(),
  getConversationRunArtifacts: mocks.getRunArtifacts,
  listConversations: vi.fn(),
  resolveConversationApproval: vi.fn(),
  resolveConversationQuestion: vi.fn(),
  selectConversationArtifact: vi.fn(),
}));

vi.mock("../../features/conversation/conversationStreamRuntime", () => ({
  conversationStreamRuntime: {
    follow: mocks.follow,
    stop: vi.fn(),
  },
  isFollowableRun: (status: string) => ["created", "queued", "running", "cancelling"].includes(status),
}));

vi.mock("../../lib/llmConfig", () => ({
  buildConversationLlmPayload: () => ({
    llm_credential_id: "credential-1",
    api_base: "https://api.openai.com/v1",
    model_name: "gpt-4.1-mini",
  }),
  getStoredApiConfig: () => ({}),
}));

vi.mock("../datasourceSelectionStore", () => ({
  useDatasourceSelectionStore: {
    getState: () => ({ activeDatasourceId: "datasource-1" }),
  },
}));

import { useConversationStore } from "../conversationStore";

const initialDetail: ConversationDetail = {
  protocol_version: 2,
  id: "conversation-1",
  title: "Orders",
  datasource_id: "datasource-1",
  context_tables: ["orders"],
  selected_artifact_id: null,
  runs: [],
  items: [],
  cursor: 10,
};

describe("conversationStore admission projection", () => {
  beforeEach(() => {
    mocks.admit.mockReset();
    mocks.create.mockReset();
    mocks.getRunArtifacts.mockReset();
    mocks.follow.mockReset().mockResolvedValue(undefined);
    useConversationStore.setState({
      summaries: [],
      activeConversationId: initialDetail.id,
      detailById: { [initialDetail.id]: initialDetail },
      artifactsById: {},
      liveFieldsById: {},
    });
  });

  it("creates a conversation without the removed manual table context", async () => {
    mocks.create.mockResolvedValue({
      ...initialDetail,
      context_tables: [],
    });

    await useConversationStore.getState().createAndOpenConversation("分析最近订单");

    expect(mocks.create).toHaveBeenCalledWith({
      datasource_id: "datasource-1",
      title: "分析最近订单",
      context_tables: [],
    });
  });

  it("shows the admitted user message and queued run before following SSE", async () => {
    mocks.admit.mockResolvedValue({
      session_id: initialDetail.id,
      input_id: "input-1",
      run_id: "run-1",
      user_message_id: "message-user-1",
      input_sequence: 1,
      event_cursor: 12,
      stream_path: `/conversations/${initialDetail.id}/stream`,
      projection: {
        cursor: 12,
        items: [
          {
            id: "message-user-1",
            type: "message",
            session_id: initialDetail.id,
            run_id: "run-1",
            payload: {
              role: "user",
              content: "分析最近订单",
              evidence: [],
              artifact_refs: [],
              limitation_codes: [],
            },
            status: "completed",
            sequence: 1,
            revision: 1,
            created_at: "2026-07-26T10:00:00Z",
            completed_at: "2026-07-26T10:00:00Z",
          },
        ],
        runs: [{
          id: "run-1",
          session_id: initialDetail.id,
          input_id: "input-1",
          session_sequence: 1,
          user_message_id: "message-user-1",
          datasource_id: "datasource-1",
          question: "分析最近订单",
          status: "queued",
          version: 0,
          current_turn_id: null,
          cancel_requested: false,
          result: {},
          error: null,
        }],
      },
    });

    const send = useConversationStore.getState().sendMessage(
      initialDetail.id,
      "分析最近订单",
      "queue",
      "intent-1",
    );

    await vi.waitFor(() => {
      const state = useConversationStore.getState();
      const item = state.detailById[initialDetail.id].items[0];
      expect(
        item?.type === "message" && item.payload.role === "user"
          ? item.payload.content
          : null,
      ).toBe("分析最近订单");
      expect(state.detailById[initialDetail.id].runs[0]?.status).toBe("queued");
    });
    await send;

    expect(mocks.follow).toHaveBeenCalledWith(
      initialDetail.id,
      "run-1",
      12,
      expect.any(Object),
    );
  });

  it("keeps loaded history and in-flight text when reconciling an authoritative snapshot", () => {
    const run = {
      id: "run-1",
      session_id: initialDetail.id,
      input_id: "input-1",
      session_sequence: 1,
      user_message_id: "message-user-1",
      datasource_id: "datasource-1",
      question: "分析最近订单",
      status: "running" as const,
      version: 1,
      current_turn_id: "turn-1",
      cancel_requested: false,
      result: {},
      error: null,
    };
    const message = {
      id: "message:run-1:turn-1",
      type: "message" as const,
      session_id: initialDetail.id,
      run_id: run.id,
      turn_id: "turn-1",
      sequence: 2,
      revision: 1,
      status: "in_progress" as const,
      created_at: "2026-07-26T10:00:00Z",
      payload: {
        role: "assistant" as const,
        phase: "commentary" as const,
        content: "",
        evidence: [],
        artifact_refs: [],
        limitation_codes: [],
      },
    };
    const historicalMessage = {
      ...message,
      id: "message-user-old",
      run_id: "run-old",
      sequence: 1,
      status: "completed" as const,
      payload: { ...message.payload, role: "user" as const, phase: null, content: "更早的问题" },
    };
    useConversationStore.setState({
      detailById: {
        [initialDetail.id]: {
          ...initialDetail,
          runs: [run],
          items: [historicalMessage, message],
        },
      },
    });
    useConversationStore.getState().applyStreamEvent({
      kind: "delta",
      delta: {
        session_id: initialDetail.id,
        run_id: run.id,
        turn_id: "turn-1",
        item_id: message.id,
        item_type: "message",
        field: "content",
        revision: 1,
        offset: 0,
        content: "正在核验订单趋势",
      },
    });

    useConversationStore.getState().loadConversation({
      ...initialDetail,
      runs: [run],
      items: [message],
      cursor: 11,
    });

    const items = useConversationStore.getState().detailById[initialDetail.id].items;
    expect(items.map((item) => item.id)).toEqual(["message-user-old", message.id]);
    const liveMessage = items.find((item) => item.id === message.id);
    expect(liveMessage?.type === "message" ? liveMessage.payload.content : "").toBe("正在核验订单趋势");
  });

  it("reloads a run when a newly referenced artifact was produced after an earlier fetch", async () => {
    const sqlArtifact = artifact("sql-1", "sql", "supporting");
    const resultArtifact = artifact("result-1", "result_view", "primary");
    mocks.getRunArtifacts
      .mockResolvedValueOnce([sqlArtifact])
      .mockResolvedValueOnce([sqlArtifact, resultArtifact]);

    await useConversationStore.getState().loadRunArtifacts(
      initialDetail.id,
      "run-1",
      ["sql-1"],
    );
    await useConversationStore.getState().loadRunArtifacts(
      initialDetail.id,
      "run-1",
      ["sql-1", "result-1"],
    );

    expect(mocks.getRunArtifacts).toHaveBeenCalledTimes(2);
    expect(useConversationStore.getState().artifactsById["result-1"]).toEqual(resultArtifact);
  });

  it("waits for an in-flight run fetch and refetches when its expected artifact is still missing", async () => {
    const sqlArtifact = artifact("sql-1", "sql", "supporting");
    const resultArtifact = artifact("result-1", "result_view", "primary");
    let resolveFirstFetch: (artifacts: ConversationArtifact[]) => void = () => undefined;
    mocks.getRunArtifacts
      .mockImplementationOnce(() => new Promise<ConversationArtifact[]>((resolve) => {
        resolveFirstFetch = resolve;
      }))
      .mockResolvedValueOnce([sqlArtifact, resultArtifact]);

    const firstLoad = useConversationStore.getState().loadRunArtifacts(
      initialDetail.id,
      "run-1",
      ["sql-1"],
    );
    const resultLoad = useConversationStore.getState().loadRunArtifacts(
      initialDetail.id,
      "run-1",
      ["result-1"],
    );
    resolveFirstFetch([sqlArtifact]);
    await Promise.all([firstLoad, resultLoad]);

    expect(mocks.getRunArtifacts).toHaveBeenCalledTimes(2);
    expect(useConversationStore.getState().artifactsById["result-1"]).toEqual(resultArtifact);
  });
});

function artifact(
  id: string,
  type: "sql" | "result_view",
  visibility: "supporting" | "primary",
): ConversationArtifact {
  const common = {
    id,
    session_id: initialDetail.id,
    run_id: "run-1",
    semantic_key: id,
    version: 1,
    type,
    title: id,
    status: "completed" as const,
    visibility,
    provenance: {},
    relations: [],
  };
  if (type === "sql") {
    return {
      ...common,
      type,
      visibility: "supporting",
      payload: {
        sql: "SELECT 1",
        safeSql: "SELECT 1",
        dialect: "sqlite",
        queryFingerprint: "sql-1",
      },
    };
  }
  return {
    ...common,
    type,
    visibility: "primary",
    payload: {
      sourceSqlArtifactId: "sql-1",
      queryFingerprint: "result-1",
      datasourceGeneration: 1,
      columns: ["value"],
      rowCount: 1,
      returnedRows: 1,
      latencyMs: 1,
      executedAt: "2026-07-26T00:00:00Z",
      truncated: false,
    },
  };
}
