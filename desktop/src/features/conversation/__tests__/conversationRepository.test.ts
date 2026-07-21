import { beforeEach, describe, expect, it, vi } from "vitest";
import { createConversation, listConversations, streamConversation } from "../conversationRepository";

vi.mock("../../../lib/api/client", () => ({
  request: vi.fn(),
  BASE_URL: "http://127.0.0.1:8000/api/v1",
  ENGINE_TOKEN: "test-token",
}));

const { request } = await import("../../../lib/api/client");

describe("conversationRepository", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("lists structured conversation summaries", async () => {
    vi.mocked(request).mockResolvedValueOnce([
      {
        id: "conv-1",
        title: "Orders",
        datasource_id: "ds-1",
        updated_at: "2026-06-21T00:00:00+00:00",
        last_message: "Done",
        message_count: 2,
        run_status: "completed",
        artifact_count: 3,
      },
    ]);

    const result = await listConversations();

    expect(result[0].id).toBe("conv-1");
    expect(result[0].message_count).toBe(2);
    expect(request).toHaveBeenCalledWith("/conversations");
  });

  it("creates a conversation through the structured endpoint", async () => {
    vi.mocked(request).mockResolvedValueOnce({
      protocol_version: 1,
      session: {
        id: "conv-2", title: "New", datasource_id: "ds-1",
        context_tables: ["orders"], context_epoch: 0, selected_artifact_id: null,
      },
      messages: [],
      runs: [],
      turns: [],
      activities: [],
      artifacts: [],
      evidence: [],
      approvals: [],
      questions: [],
      cursor: 0,
    });

    const result = await createConversation({
      datasource_id: "ds-1",
      title: "New",
      context_tables: ["orders"],
    });

    expect(result.id).toBe("conv-2");
    expect(request).toHaveBeenCalledWith("/conversations", {
      method: "POST",
      body: JSON.stringify({ datasource_id: "ds-1", title: "New", context_tables: ["orders"] }),
    });
  });

  it("parses fragmented and multi-line SSE frames with the standard parser", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      ": heartbeat\n\nevent: live.delta\ndata: {\"run_id\":\"run-1\",\ndata: \"channel\":\"text\",\"offset\":0,\"content\":\"Hi\"}\n\n",
      "event: runtime\nid: 8\ndata: {\"sequence\":8,\"run_id\":\"run-1\",\"event_type\":\"run.completed\",\"payload\":{}}\n\n",
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }), { status: 200 })));
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
});
