import { describe, expect, it } from "vitest";
import type {
  AssistantMessageItem,
  ConversationDetail,
  ConversationRun,
  RuntimeEventEnvelope,
} from "../../types/conversation";
import type { ConversationStore } from "../conversationStore";
import { reduceStreamEvent, removeConversationState } from "../conversationStoreReducer";

describe("conversationStoreReducer", () => {
  it("removes all state owned by a deleted conversation", () => {
    const current = state();
    current.artifactsById["artifact-1"] = {
      id: "artifact-1",
      session_id: "session-1",
      run_id: "run-1",
      version: 1,
      type: "result_view",
      title: "结果",
      status: "completed",
      visibility: "primary",
      payload: {},
      provenance: {},
      relations: [],
    };
    const next = removeConversationState(current, "session-1");
    expect(next.detailById["session-1"]).toBeUndefined();
    expect(next.artifactsById["artifact-1"]).toBeUndefined();
  });

  it("applies append-only answer deltas and rejects duplicates or gaps", () => {
    const first = reduceStreamEvent(state(), {
      kind: "delta",
      delta: delta(1, 0, "你"),
    });
    expect(answerText(first)).toBe("你");

    const duplicate = reduceStreamEvent(first, {
      kind: "delta",
      delta: delta(1, 0, "你"),
    });
    expect(duplicate).toBe(first);

    const gap = reduceStreamEvent(first, {
      kind: "delta",
      delta: delta(3, 1, "好"),
    });
    expect(gap).toBe(first);

    const second = reduceStreamEvent(first, {
      kind: "delta",
      delta: delta(2, 1, "好"),
    });
    expect(answerText(second)).toBe("你好");
  });

  it("uses Unicode code-point offsets for multilingual streaming", () => {
    const first = reduceStreamEvent(state(), {
      kind: "delta",
      delta: delta(1, 0, "😀"),
    });
    const second = reduceStreamEvent(first, {
      kind: "delta",
      delta: delta(2, 1, "完成"),
    });
    expect(answerText(second)).toBe("😀完成");
  });

  it("rebases from an authoritative offset-zero live snapshot", () => {
    const first = reduceStreamEvent(state(), {
      kind: "delta",
      delta: delta(1, 0, "旧"),
    });
    const rebased = reduceStreamEvent(first, {
      kind: "delta",
      delta: delta(4, 0, "权威快照"),
    });
    expect(answerText(rebased)).toBe("权威快照");
    expect(rebased.liveFieldsById["run-1:message:run-1:turn-1:content"]).toEqual({
      revision: 4,
      offset: 4,
    });
  });

  it("advances across deltas already covered by a newer committed snapshot", () => {
    const first = reduceStreamEvent(state(), {
      kind: "delta",
      delta: delta(1, 0, "你"),
    });
    const committed: RuntimeEventEnvelope = {
      event_id: "event-committed-snapshot",
      event_type: "run.item.updated",
      event_version: 1,
      session_id: "session-1",
      run_id: "run-1",
      turn_id: "turn-1",
      sequence: 2,
      timestamp: "2026-07-26T00:00:01Z",
      payload: {
        item: {
          ...answer(),
          revision: 2,
          payload: { ...answer().payload, content: "你好" },
        },
      },
    };
    const snapshotted = reduceStreamEvent(first, { kind: "event", event: committed });

    const covered = reduceStreamEvent(snapshotted, {
      kind: "delta",
      delta: delta(2, 1, "好"),
    });
    expect(answerText(covered)).toBe("你好");
    expect(covered.liveFieldsById["run-1:message:run-1:turn-1:content"]).toEqual({
      revision: 2,
      offset: 2,
    });

    const continued = reduceStreamEvent(covered, {
      kind: "delta",
      delta: delta(3, 2, "！"),
    });
    expect(answerText(continued)).toBe("你好！");
  });

  it("projects canonical run and item payloads and deduplicates by session cursor", () => {
    const completedRun = { ...run(), status: "completed" as const, version: 2 };
    const completedAnswer = {
      ...answer(),
      status: "completed" as const,
      revision: 2,
      payload: { ...answer().payload, content: "最终答案" },
    };
    const event: RuntimeEventEnvelope = {
      event_id: "event-1",
      event_type: "run.item.completed",
      event_version: 1,
      session_id: "session-1",
      run_id: "run-1",
      turn_id: "turn-1",
      sequence: 2,
      timestamp: "2026-07-26T00:01:00Z",
      payload: { run: completedRun, item: completedAnswer },
    };
    const once = reduceStreamEvent(state(), { kind: "event", event });
    const twice = reduceStreamEvent(once, { kind: "event", event });
    expect(once.detailById["session-1"].runs[0].status).toBe("completed");
    expect(answerText(once)).toBe("最终答案");
    expect(twice).toBe(once);
  });

  it("ignores late live deltas after a run becomes terminal", () => {
    const current = state();
    current.detailById["session-1"].runs[0] = { ...run(), status: "completed" };
    const next = reduceStreamEvent(current, {
      kind: "delta",
      delta: delta(1, 0, "不应出现"),
    });
    expect(next).toBe(current);
  });
});

function state(): ConversationStore {
  const detail: ConversationDetail = {
    protocol_version: 2,
    id: "session-1",
    title: "测试",
    datasource_id: "ds-1",
    context_tables: [],
    runs: [run()],
    items: [answer()],
    cursor: 0,
  };
  return {
    summaries: [],
    activeConversationId: "session-1",
    detailById: { "session-1": detail },
    artifactsById: {},
    liveFieldsById: {},
  } as unknown as ConversationStore;
}

function run(): ConversationRun {
  return {
    id: "run-1",
    session_id: "session-1",
    input_id: "input-1",
    session_sequence: 1,
    user_message_id: "user-1",
    datasource_id: "ds-1",
    question: "问题",
    status: "running",
    version: 1,
    current_turn_id: "turn-1",
    cancel_requested: false,
    result: {},
    error: null,
  };
}

function answer(): AssistantMessageItem {
  return {
    id: "message:run-1:turn-1",
    type: "message",
    session_id: "session-1",
    run_id: "run-1",
    turn_id: "turn-1",
    sequence: 1,
    revision: 1,
    status: "in_progress",
    created_at: "2026-07-26T00:00:00Z",
    payload: {
      role: "assistant",
      phase: "final_answer",
      content: "",
      evidence: [],
      artifact_refs: [],
      limitation_codes: [],
    },
  };
}

function delta(revision: number, offset: number, content: string) {
  return {
    session_id: "session-1",
    run_id: "run-1",
    turn_id: "turn-1",
    item_id: "message:run-1:turn-1",
    item_type: "message" as const,
    field: "content" as const,
    revision,
    offset,
    content,
  };
}

function answerText(current: ConversationStore): string {
  const item = current.detailById["session-1"].items
    .find((candidate) => candidate.id === "message:run-1:turn-1")!;
  return item.type === "message" ? item.payload.content : "";
}
