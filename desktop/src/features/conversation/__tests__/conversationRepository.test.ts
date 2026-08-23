import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  admitConversationInput,
  createConversation,
  listConversations,
  ConversationProtocolError,
  streamConversation,
} from "../conversationRepository";

const sdkMocks = vi.hoisted(() => ({
  admitInput: vi.fn(),
  createConversation: vi.fn(),
  fetchEnginePath: vi.fn(),
  listConversations: vi.fn(),
}));

vi.mock("../../../lib/api/generated/sdk.gen", () => ({
  admitConversationInputApiV1ConversationsConversationIdInputsPost: sdkMocks.admitInput,
  createConversationApiV1ConversationsPost: sdkMocks.createConversation,
  listConversationsApiV1ConversationsGet: sdkMocks.listConversations,
}));

vi.mock("../../../lib/api/client", () => ({
  ApiError: class ApiError extends Error {},
  fetchEnginePath: sdkMocks.fetchEnginePath,
}));

const pagination = {
  items: { has_more: false, next_before_sequence: null },
  runs: { has_more: false, next_before_sequence: null },
};

const projectedRun = (
  id: string,
  status: "running" | "completed",
) => ({
  id,
  session_id: "conv-1",
  input_id: `input-${id}`,
  session_sequence: 1,
  user_message_id: `message-${id}`,
  question: "Analyze data",
  status,
  version: 1,
  current_turn_id: null,
  cancel_requested: false,
  result: {},
  error: null,
});

const runtimeEvent = (
  sequence: number,
  eventType: "run.started" | "run.completed",
  runId: string,
  status: "running" | "completed",
) => ({
  event_id: `event-${sequence}`,
  event_type: eventType,
  event_version: 1,
  session_id: "conv-1",
  run_id: runId,
  turn_id: null,
  sequence,
  timestamp: "2026-06-21T00:00:00Z",
  payload: { run: projectedRun(runId, status) },
});

describe("conversationRepository", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("lists structured conversation summaries", async () => {
    sdkMocks.listConversations.mockResolvedValueOnce({
      data: [
        {
          id: "conv-1",
          title: "Orders",
          project_id: "project-1",
          updated_at: "2026-06-21T00:00:00+00:00",
          last_message: "Done",
          message_count: 2,
          run_status: "completed",
          artifact_count: 3,
        },
      ],
    });

    const result = await listConversations();

    expect(result[0].id).toBe("conv-1");
    expect(result[0].message_count).toBe(2);
    expect(sdkMocks.listConversations).toHaveBeenCalledWith({ throwOnError: true });
  });

  it("creates a conversation through the structured endpoint", async () => {
    sdkMocks.createConversation.mockResolvedValueOnce({
      data: {
        protocol_version: 2,
        session: {
          id: "conv-2", project_id: "project-1", title: "New",
          resource_intents: [{ kind: "dbfox.data.database", id: "ds-1" }], context_epoch: 0, selected_artifact_id: null,
        },
        runs: [],
        items: [],
        pagination,
        cursor: 0,
      },
    });

    const result = await createConversation({
      project_id: "project-1",
      title: "New",
      resource_intents: [{ kind: "dbfox.data.database", id: "ds-1" }],
    });

    expect(result.id).toBe("conv-2");
    expect(sdkMocks.createConversation).toHaveBeenCalledWith({
      body: { project_id: "project-1", title: "New", resource_intents: [{ kind: "dbfox.data.database", id: "ds-1" }] },
      throwOnError: true,
    });
  });

  it("creates a conversation with project_id and normalizes project_id in snapshot", async () => {
    sdkMocks.createConversation.mockResolvedValueOnce({
      data: {
        protocol_version: 2,
        session: {
          id: "conv-p4",
          project_id: "proj-100",
          title: "Project-scoped session",
          resource_intents: [],
          context_epoch: 0,
          selected_artifact_id: null,
        },
        runs: [],
        items: [],
        pagination,
        cursor: 0,
      },
    });

    const result = await createConversation({
      project_id: "proj-100",
      title: "Project-scoped session",
      resource_intents: [],
    });

    expect(result.id).toBe("conv-p4");
    expect(result.project_id).toBe("proj-100");
    expect(sdkMocks.createConversation).toHaveBeenCalledWith({
      body: { project_id: "proj-100", title: "Project-scoped session", resource_intents: [] },
      throwOnError: true,
    });
  });

  it("rejects snapshots from an unsupported timeline protocol", async () => {
    sdkMocks.createConversation.mockResolvedValueOnce({
      data: {
        protocol_version: 1,
        session: {
          id: "conv-old", project_id: "project-1", title: "Old",
          resource_intents: [], context_epoch: 0, selected_artifact_id: null,
        },
        runs: [],
        items: [],
        pagination,
        cursor: 0,
      },
    });

    await expect(createConversation({
      project_id: "project-1",
      resource_intents: [],
    })).rejects.toThrow("智能分析返回了无法识别的数据，请刷新后重试。");
  });

  it("rejects admission projections from an unsupported timeline protocol", async () => {
    sdkMocks.admitInput.mockResolvedValueOnce({
      data: {
        session_id: "conv-2",
        input_id: "input-1",
        run_id: "run-1",
        user_message_id: "message-1",
        input_sequence: 1,
        event_cursor: 1,
        stream_path: "/stream",
        projection: { protocol_version: 1, cursor: 1, items: [], runs: [] },
      },
    });

    await expect(admitConversationInput("conv-2", {
      content: "分析数据",
      idempotency_key: "input-1",
      delivery_mode: "queue",
      selected_artifact_ids: [],
      workspace_context: {},
      llm_credential_id: "credential-1",
    })).rejects.toThrow("智能分析返回了无法识别的数据，请刷新后重试。");
  });

  it("parses fragmented and multi-line SSE frames with the standard parser", async () => {
    const encoder = new TextEncoder();
    const completed = JSON.stringify(runtimeEvent(8, "run.completed", "run-1", "completed"));
    const chunks = [
      ": heartbeat\n\nevent: run.item.delta\ndata: {\"session_id\":\"conv-1\",\"run_id\":\"run-1\",\"item_id\":\"message:run-1:turn-1\",\"item_type\":\"message\",\"field\":\"content\",\"revision\":1,\"offset\":0,\"content\":\"Hi\"}\n\n",
      `event: run.completed\nid: 8\ndata: ${completed}\n\n`,
    ];
    sdkMocks.fetchEnginePath.mockResolvedValue(new Response(new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }), { status: 200 }));
    const events: unknown[] = [];

    const cursor = await streamConversation("conv-1", {
      afterSequence: 4,
      targetRunId: "run-1",
      onEvent: (event) => events.push(event),
    });

    expect(cursor).toBe(8);
    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({ kind: "delta", delta: { content: "Hi" } });
    expect(events[1]).toMatchObject({ kind: "event", event: { event_type: "run.completed" } });
  });

  it("keeps a terminal boundary sticky when a later event shares the same chunk", async () => {
    const encoder = new TextEncoder();
    let cancelled = false;
    const completed = JSON.stringify(runtimeEvent(8, "run.completed", "run-1", "completed"));
    const started = JSON.stringify(runtimeEvent(9, "run.started", "run-2", "running"));
    const chunk = [
      `event: run.completed\nid: 8\ndata: ${completed}\n\n`,
      `event: run.started\nid: 9\ndata: ${started}\n\n`,
    ].join("");
    sdkMocks.fetchEnginePath.mockResolvedValue(new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(chunk));
      },
      cancel() {
        cancelled = true;
      },
    }), { status: 200 }));

    const cursor = await streamConversation("conv-1", {
      afterSequence: 4,
      targetRunId: "run-1",
      onEvent: () => undefined,
    });

    expect(cursor).toBe(9);
    expect(cancelled).toBe(true);
  });

  it("wraps malformed stream payloads as a safe non-retryable protocol error", async () => {
    const encoder = new TextEncoder();
    sdkMocks.fetchEnginePath.mockResolvedValue(new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("event: run.updated\ndata: {invalid}\n\n"));
        controller.close();
      },
    }), { status: 200 }));

    await expect(streamConversation("conv-1", {
      afterSequence: 0,
      targetRunId: "run-1",
      onEvent: () => undefined,
    })).rejects.toBeInstanceOf(ConversationProtocolError);
  });
});
