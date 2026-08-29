import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact, ConversationDetail } from "../../types/conversation";

const mocks = vi.hoisted(() => ({
  admit: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  history: vi.fn(),
  getRunArtifacts: vi.fn(),
  follow: vi.fn(),
}));

vi.mock("../../features/conversation/conversationRepository", () => ({
  admitConversationInput: mocks.admit,
  cancelConversationRun: vi.fn(),
  createConversation: mocks.create,
  deleteConversation: vi.fn(),
  getConversation: mocks.get,
  getConversationHistory: mocks.history,
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

vi.mock("../workspaceStore", () => ({
  useWorkspaceStore: {
    getState: () => ({ activeProjectId: "project-1" }),
  },
}));

import { useConversationStore } from "../conversationStore";

const initialDetail: ConversationDetail = {
  protocol_version: 2,
  id: "conversation-1",
  title: "Orders",
  project_id: "project-1",
  resource_intents: [{ kind: "dbfox.data.database", id: "datasource-1" }],
  selected_artifact_id: null,
  runs: [],
  items: [],
  cursor: 10,
};

describe("conversationStore admission projection", () => {
  beforeEach(() => {
    mocks.admit.mockReset();
    mocks.create.mockReset();
    mocks.get.mockReset();
    mocks.history.mockReset();
    mocks.getRunArtifacts.mockReset();
    mocks.follow.mockReset().mockResolvedValue(undefined);
    useConversationStore.setState({
      summaries: [],
      detailById: { [initialDetail.id]: initialDetail },
      artifactsById: {},
      liveFieldsById: {},
      streamErrorById: {},
      streamStateById: {},
    });
  });

  it("clears a stale stream failure after refreshing a terminal snapshot", async () => {
    mocks.get.mockResolvedValue(initialDetail);
    useConversationStore.setState({
      streamErrorById: { [initialDetail.id]: "实时流协议无法继续" },
      streamStateById: { [initialDetail.id]: "failed" },
    });

    await useConversationStore.getState().openConversation(initialDetail.id);

    expect(useConversationStore.getState().streamErrorById[initialDetail.id]).toBeUndefined();
    expect(useConversationStore.getState().streamStateById[initialDetail.id]).toBe("idle");
    expect(mocks.follow).not.toHaveBeenCalled();
  });

  it("creates a conversation without the removed manual table context", async () => {
    mocks.create.mockResolvedValue({
      ...initialDetail,
    });

    await useConversationStore.getState().createAndOpenConversation("分析最近订单");

    expect(mocks.create).toHaveBeenCalledWith({
      project_id: "project-1",
      title: "分析最近订单",
      resource_intents: [],
    });
    expect(useConversationStore.getState().summaries).toContainEqual(
      expect.objectContaining({ id: initialDetail.id, project_id: "project-1" }),
    );
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

    expect(mocks.admit).toHaveBeenCalledWith(
      initialDetail.id,
      expect.not.objectContaining({ requested_resources: expect.anything() }),
    );
    expect(mocks.admit.mock.calls[0]?.[1]).toEqual(expect.objectContaining({
      workspace_context: expect.not.objectContaining({ datasource_id: expect.anything() }),
    }));

    expect(mocks.follow).toHaveBeenCalledWith(
      initialDetail.id,
      "run-1",
      12,
      expect.any(Object),
    );
  });

  it("submits a Workbench reference without duplicating its authority", async () => {
    mocks.admit.mockResolvedValue({
      run_id: "run-1",
      event_cursor: 12,
      projection: {
        ...initialDetail,
        cursor: 12,
        items: [],
        runs: [],
      },
    });

    await useConversationStore.getState().sendMessage(
      initialDetail.id,
      "写一首钢琴曲",
      "queue",
      "intent-music-1",
      [{
        label: "Piano Studio",
        authority: { kind: "dbfox.music.library", id: "project-1" },
      }],
    );

    expect(mocks.admit).toHaveBeenCalledWith(
      initialDetail.id,
      expect.objectContaining({
        content: "写一首钢琴曲",
        references: [{
          label: "Piano Studio",
          authority: { kind: "dbfox.music.library", id: "project-1" },
          object: null,
          locator: null,
          artifact_id: null,
        }],
      }),
    );
    expect(mocks.admit.mock.calls[0]?.[1]).not.toHaveProperty("requested_resources");
  });

  it("keeps loaded history and in-flight text when reconciling an authoritative snapshot", () => {
    const run = {
      id: "run-1",
      session_id: initialDetail.id,
      input_id: "input-1",
      session_sequence: 1,
      user_message_id: "message-user-1",
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

  it("prepends an authoritative bounded history page and advances both cursors", async () => {
    const makeRun = (id: string, sequence: number): ConversationDetail["runs"][number] => ({
      id,
      session_id: initialDetail.id,
      input_id: `input-${sequence}`,
      session_sequence: sequence,
      user_message_id: `user-${sequence}`,
      question: `问题 ${sequence}`,
      status: "completed",
      version: 1,
      current_turn_id: null,
      cancel_requested: false,
      result: {},
      error: null,
    });
    const makeMessage = (
      runId: string,
      id: string,
      sequence: number,
      content: string,
    ): ConversationDetail["items"][number] => ({
      id,
      type: "message",
      session_id: initialDetail.id,
      run_id: runId,
      sequence,
      revision: 1,
      status: "completed",
      created_at: `2026-07-26T00:00:${String(sequence).padStart(2, "0")}Z`,
      completed_at: `2026-07-26T00:00:${String(sequence).padStart(2, "0")}Z`,
      payload: {
        role: "user",
        content,
        evidence: [],
        artifact_refs: [],
        limitation_codes: [],
      },
    });
    const current: ConversationDetail = {
      ...initialDetail,
      runs: [makeRun("run-2", 2)],
      items: [makeMessage("run-2", "user-2", 3, "当前问题")],
      pagination: {
        items: { has_more: true, next_before_sequence: 3 },
        runs: { has_more: true, next_before_sequence: 2 },
      },
    };
    const olderPage: ConversationDetail = {
      ...initialDetail,
      runs: [makeRun("run-1", 1)],
      items: [makeMessage("run-1", "user-1", 1, "更早问题")],
      pagination: {
        items: { has_more: false, next_before_sequence: null },
        runs: { has_more: false, next_before_sequence: null },
      },
      cursor: 8,
    };
    useConversationStore.setState({
      detailById: { [initialDetail.id]: current },
    });
    mocks.history.mockResolvedValue(olderPage);

    const hasMore = await useConversationStore.getState().loadOlderHistory(initialDetail.id);

    expect(mocks.history).toHaveBeenCalledWith(initialDetail.id, {
      beforeItemSequence: 3,
      beforeRunSequence: 2,
    });
    const merged = useConversationStore.getState().detailById[initialDetail.id];
    expect(merged.runs.map((run) => run.id)).toEqual(["run-1", "run-2"]);
    expect(merged.items.map((item) => item.id)).toEqual(["user-1", "user-2"]);
    expect(merged.pagination).toEqual(olderPage.pagination);
    expect(merged.cursor).toBe(10);
    expect(hasMore).toBe(false);
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
