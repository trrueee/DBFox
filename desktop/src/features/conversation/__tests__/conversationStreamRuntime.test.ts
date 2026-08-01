import { describe, expect, it, vi } from "vitest";
import type {
  ConversationDetail,
  ConversationStreamEvent,
} from "../../../types/conversation";
import { ConversationStreamRuntime } from "../conversationStreamRuntime";

function snapshot(status: "running" | "completed"): ConversationDetail {
  return {
    protocol_version: 2,
    id: "conversation-1",
    title: "Test",
    datasource_id: "datasource-1",
    context_tables: [],
    items: [],
    runs: [{
      id: "run-1",
      session_id: "conversation-1",
      input_id: "input-1",
      datasource_id: "datasource-1",
      session_sequence: 1,
      user_message_id: "message-1",
      question: "test",
      status,
      version: 1,
      cancel_requested: false,
      result: {},
      error: null,
    }],
    cursor: 4,
  };
}

describe("ConversationStreamRuntime", () => {
  it("owns retries and finishes lifecycle from an authoritative snapshot", async () => {
    const stream = vi.fn()
      .mockRejectedValueOnce(new Error("temporary disconnect"))
      .mockResolvedValueOnce(4);
    const loadSnapshot = vi.fn();
    const runtime = new ConversationStreamRuntime({
      stream,
      snapshot: vi.fn()
        .mockResolvedValueOnce(snapshot("running"))
        .mockResolvedValueOnce(snapshot("completed")),
      wait: vi.fn().mockResolvedValue(undefined),
    });

    await runtime.follow("conversation-1", "run-1", 0, {
      applyEvents: vi.fn(),
      loadSnapshot,
    });

    expect(stream).toHaveBeenCalledTimes(2);
    expect(loadSnapshot).toHaveBeenCalledWith(
      expect.objectContaining({ cursor: 4 }),
    );
    expect(runtime.lifecycle.get("conversation-1")).toBeUndefined();
  });

  it("reconnects after the latest durable event when a stream fails mid-flight", async () => {
    const durableEvent: ConversationStreamEvent = {
      kind: "event",
      event: {
        event_id: "event-3",
        event_type: "run.updated",
        event_version: 1,
        session_id: "conversation-1",
        run_id: "run-1",
        turn_id: null,
        sequence: 3,
        timestamp: "2026-07-29T00:00:00Z",
        payload: {},
      },
    };
    const stream = vi.fn()
      .mockImplementationOnce(async (_conversationId, options) => {
        options.onEvent(durableEvent);
        throw new Error("connection lost after event");
      })
      .mockResolvedValueOnce(4);
    const runtime = new ConversationStreamRuntime({
      stream,
      snapshot: vi.fn()
        .mockResolvedValueOnce({ ...snapshot("running"), cursor: 3 })
        .mockResolvedValueOnce(snapshot("completed")),
      wait: vi.fn().mockResolvedValue(undefined),
    });

    await runtime.follow("conversation-1", "run-1", 0, {
      applyEvents: vi.fn(),
      loadSnapshot: vi.fn(),
    });

    expect(stream).toHaveBeenNthCalledWith(
      2,
      "conversation-1",
      expect.objectContaining({ afterSequence: 3 }),
    );
  });

  it("aborts the prior transport when another Run starts in the same conversation", () => {
    const runtime = new ConversationStreamRuntime({
      stream: vi.fn(),
      snapshot: vi.fn(),
      wait: vi.fn(),
    });
    const first = runtime.lifecycle.start("conversation-1", "run-1");
    runtime.lifecycle.start("conversation-1", "run-2");

    expect(first.controller.signal.aborted).toBe(true);
    expect(runtime.lifecycle.get("conversation-1")?.runId).toBe("run-2");
  });
});
