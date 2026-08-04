import { describe, expect, it } from "vitest";

import {
  parseConversationRunItem,
  parseRuntimeEvent,
} from "../conversationWireSchema";

const messageItem = {
  id: "item-1",
  session_id: "session-1",
  run_id: "run-1",
  turn_id: null,
  sequence: 1,
  revision: 1,
  status: "completed",
  created_at: "2026-08-04T00:00:00Z",
  completed_at: "2026-08-04T00:00:01Z",
  type: "message",
  payload: {
    role: "assistant",
    phase: "final_answer",
    content: "done",
  },
} as const;

describe("conversation wire discriminators", () => {
  it("parses a generated run-item discriminator without an undefined branch", () => {
    expect(parseConversationRunItem(messageItem)).toMatchObject({
      id: "item-1",
      type: "message",
      payload: { content: "done" },
    });
  });

  it("parses a runtime event carrying the same discriminated item", () => {
    expect(parseRuntimeEvent({
      event_id: "event-1",
      event_type: "run.item.completed",
      event_version: 1,
      payload: { item: messageItem },
      run_id: "run-1",
      sequence: 1,
      session_id: "session-1",
      timestamp: "2026-08-04T00:00:01Z",
      turn_id: null,
    })).toMatchObject({
      event_id: "event-1",
      payload: { item: { id: "item-1", type: "message" } },
    });
  });
});
