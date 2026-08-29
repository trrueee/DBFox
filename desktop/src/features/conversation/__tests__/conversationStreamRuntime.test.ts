import { describe, expect, it, vi } from "vitest";
import type {
  ConversationDetail,
  ConversationStreamEvent,
} from "../../../types/conversation";
import { ConversationStreamRuntime } from "../conversationStreamRuntime";
import {
  ConversationProtocolError,
  ConversationStreamHttpError,
} from "../conversationRepository";

function snapshot(status: "running" | "completed"): ConversationDetail {
  return {
    protocol_version: 2,
    id: "conversation-1",
    title: "Test",
    project_id: "project-1",
    resource_intents: [],
    items: [],
    runs: [{
      id: "run-1",
      session_id: "conversation-1",
      input_id: "input-1",
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
      .mockRejectedValueOnce(new TypeError("temporary disconnect"))
      .mockResolvedValueOnce(4);
    const loadSnapshot = vi.fn();
    const onConnectionState = vi.fn();
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
      onConnectionState,
    });

    expect(stream).toHaveBeenCalledTimes(2);
    expect(loadSnapshot).toHaveBeenCalledWith(
      expect.objectContaining({ cursor: 4 }),
    );
    expect(runtime.lifecycle.get("conversation-1")).toBeUndefined();
    expect(onConnectionState.mock.calls.map(([state]) => state)).toEqual([
      "connecting",
      "reconnecting",
      "recovered",
      "reconnecting",
      "idle",
    ]);
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
        throw new TypeError("connection lost after event");
      })
      .mockResolvedValueOnce(4);
    const runtime = new ConversationStreamRuntime({
      stream,
      snapshot: vi.fn()
        .mockResolvedValueOnce({ ...snapshot("running"), cursor: 3 })
        .mockResolvedValueOnce(snapshot("completed")),
      wait: vi.fn().mockResolvedValue(undefined),
    });
    const onConnectionState = vi.fn();

    await runtime.follow("conversation-1", "run-1", 0, {
      applyEvents: vi.fn(),
      loadSnapshot: vi.fn(),
      onConnectionState,
    });

    expect(stream).toHaveBeenNthCalledWith(
      2,
      "conversation-1",
      expect.objectContaining({ afterSequence: 3 }),
    );
    expect(onConnectionState.mock.calls.map(([state]) => state)).toEqual([
      "connecting",
      "live",
      "reconnecting",
      "recovered",
      "reconnecting",
      "idle",
    ]);
  });

  it("recovers an expired event cursor from the authoritative snapshot without replay", async () => {
    const loadSnapshot = vi.fn();
    const onConnectionState = vi.fn();
    const stream = vi.fn()
      .mockRejectedValueOnce(new ConversationStreamHttpError(409))
      .mockResolvedValueOnce(4);
    const runtime = new ConversationStreamRuntime({
      stream,
      snapshot: vi.fn()
        .mockResolvedValueOnce(snapshot("running"))
        .mockResolvedValueOnce(snapshot("completed")),
      wait: vi.fn().mockResolvedValue(undefined),
    });

    await runtime.follow("conversation-1", "run-1", 1, {
      applyEvents: vi.fn(),
      loadSnapshot,
      onConnectionState,
    });

    expect(stream).toHaveBeenCalledTimes(2);
    expect(loadSnapshot).toHaveBeenCalledWith(expect.objectContaining({ cursor: 4 }));
    expect(onConnectionState.mock.calls.map(([state]) => state)).toEqual([
      "connecting",
      "recovering_snapshot",
      "recovered",
      "reconnecting",
      "idle",
    ]);
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

  it("stops permanently and reports a protocol failure instead of reconnecting forever", async () => {
    const error = new ConversationProtocolError(new Error("schema detail"));
    const stream = vi.fn().mockRejectedValue(error);
    const onError = vi.fn();
    const onConnectionState = vi.fn();
    const runtime = new ConversationStreamRuntime({
      stream,
      snapshot: vi.fn(),
      wait: vi.fn(),
    });

    await runtime.follow("conversation-1", "run-1", 0, {
      applyEvents: vi.fn(),
      loadSnapshot: vi.fn(),
      onError,
      onConnectionState,
    });

    expect(stream).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(error);
    expect(onConnectionState.mock.calls.map(([state]) => state)).toEqual([
      "connecting",
      "failed",
    ]);
    expect(runtime.lifecycle.get("conversation-1")).toBeUndefined();
  });
});
