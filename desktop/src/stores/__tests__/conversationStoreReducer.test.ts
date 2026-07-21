import { describe, expect, it } from "vitest";
import type { ConversationStore } from "../conversationStore";
import { reduceStreamEvent } from "../conversationStoreReducer";

function state(): ConversationStore {
  const message = {
    id: "message-assistant", conversation_id: "session-1", role: "assistant" as const,
    content: "", status: "created" as const, sequence: 2, created_at: null, updated_at: null,
  };
  const run = {
    id: "run-1", conversation_id: "session-1", datasource_id: "ds-1", question: "统计订单",
    assistant_message_id: message.id, status: "running" as const,
  };
  const detail = {
    protocol_version: 1 as const,
    id: "session-1", title: "订单", datasource_id: "ds-1", context_tables: [],
    messages: [message], runs: [run], activities: [], artifacts: [], evidence: [], approvals: [],
    questions: [], cursor: 0,
  };
  return {
    summaries: [], activeConversationId: "session-1", detailById: { "session-1": detail },
    messagesById: { [message.id]: message }, runsById: { [run.id]: run }, artifactsById: {},
    liveRevisionById: {},
    abortControllers: new Map(),
  } as unknown as ConversationStore;
}

describe("conversationStoreReducer", () => {
  it("merges live answer deltas into the exact assistant message", () => {
    const next = reduceStreamEvent(state(), { kind: "delta", delta: {
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1",
      channel: "answer", operation: "append", live_id: "live:session-1:run-1:turn-1:answer",
      channel_revision: 1, correlation_id: "message-assistant", content: "已找到订单数据",
    } });
    expect(next.messagesById["message-assistant"].content).toBe("已找到订单数据");
    expect(next.messagesById["message-assistant"].status).toBe("streaming");
  });

  it("deduplicates live revisions and rejects a channel gap", () => {
    const delta = { kind: "delta" as const, delta: {
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1",
      channel: "answer" as const, operation: "append" as const, live_id: "live:session-1:run-1:turn-1:answer",
      channel_revision: 1, correlation_id: "message-assistant", content: "A",
    } };
    const once = reduceStreamEvent(state(), delta);
    const duplicate = reduceStreamEvent(once, delta);
    const gap = reduceStreamEvent(once, {
      ...delta,
      delta: { ...delta.delta, channel_revision: 3, content: "C" },
    });
    expect(once.messagesById["message-assistant"].content).toBe("A");
    expect(duplicate).toBe(once);
    expect(gap).toBe(once);
  });

  it("rebases a reconnected live channel before applying new deltas", () => {
    const rebased = reduceStreamEvent(state(), { kind: "delta", delta: {
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1",
      channel: "answer", operation: "replace", live_id: "live:session-1:run-1:turn-1:answer",
      channel_revision: 7, correlation_id: "message-assistant", content: "完整草稿",
    } });
    const appended = reduceStreamEvent(rebased, { kind: "delta", delta: {
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1",
      channel: "answer", operation: "append", live_id: "live:session-1:run-1:turn-1:answer",
      channel_revision: 8, correlation_id: "message-assistant", content: "继续",
    } });

    expect(rebased.messagesById["message-assistant"].content).toBe("完整草稿");
    expect(appended.messagesById["message-assistant"].content).toBe("完整草稿继续");
  });

  it("deduplicates committed events by the Session cursor", () => {
    const event = { kind: "event" as const, event: {
      event_id: "event-1", event_type: "run.completed", event_version: 1,
      session_id: "session-1", run_id: "run-1", sequence: 1,
      timestamp: "2026-07-19T00:00:00Z", payload: { run: { version: 4 } },
    } };
    const once = reduceStreamEvent(state(), event);
    const twice = reduceStreamEvent(once, event);
    expect(once.runsById["run-1"].status).toBe("completed");
    expect(twice).toBe(once);
  });

  it("projects a durable clarification request without treating it as approval", () => {
    const next = reduceStreamEvent(state(), { kind: "event", event: {
      event_id: "event-question", event_type: "question.requested", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 1,
      timestamp: "2026-07-19T00:00:00Z", payload: { question: {
        id: "question-1", run_id: "run-1", turn_id: "turn-1", status: "pending", version: 0,
        question: "选择口径", reason: "结果不同", options: [], allow_free_text: true,
      } },
    } });
    expect(next.runsById["run-1"].status).toBe("waiting_input");
    expect(next.detailById["session-1"].questions?.[0].id).toBe("question-1");
    expect(next.runsById["run-1"].approval).toBeUndefined();
  });

  it("uses one canonical activity identity for live and durable turn state", () => {
    const started = reduceStreamEvent(state(), { kind: "event", event: {
      event_id: "event-turn-start", event_type: "turn.started", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 1,
      timestamp: "2026-07-19T00:00:00Z", payload: { turn: { id: "turn-1" } },
    } });
    const live = reduceStreamEvent(started, { kind: "delta", delta: {
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1",
      channel: "reasoning_summary", operation: "append", live_id: "live:session-1:run-1:turn-1:reasoning_summary",
      channel_revision: 1, correlation_id: "activity:turn-1:analysis",
      content: "正在检查订单与用户的关联。",
    } });
    const completed = reduceStreamEvent(live, { kind: "event", event: {
      event_id: "event-turn-complete", event_type: "turn.completed", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 2,
      timestamp: "2026-07-19T00:00:01Z", payload: { turn: {
        id: "turn-1", reasoning_summary: "已确认订单与用户的关联。", tool_call_count: 1,
      } },
    } });
    const activities = completed.detailById["session-1"].activities || [];
    expect(activities).toHaveLength(1);
    expect(activities[0]).toMatchObject({
      id: "activity:turn-1:analysis", status: "completed",
      title: "已确定下一步分析动作", summary: "已确认订单与用户的关联。",
    });
  });

  it("links a settled tool activity to its result Artifact", () => {
    const requested = reduceStreamEvent(state(), { kind: "event", event: {
      event_id: "event-tool", event_type: "tool.requested", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 1,
      timestamp: "2026-07-19T00:00:00Z", payload: { tool_invocation: {
        id: "tool-1", tool_name: "sql.execute_readonly", status: "requested",
      } },
    } });
    const observed = reduceStreamEvent(requested, { kind: "event", event: {
      event_id: "event-observation", event_type: "observation.created", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 2,
      timestamp: "2026-07-19T00:00:01Z", payload: { observation: {
        tool_invocation_id: "tool-1", model_visible_summary: "查询成功，返回 1 行。",
        artifact_ids: ["artifact_result"],
      } },
    } });
    expect(observed.detailById["session-1"].activities?.[0]).toMatchObject({
      id: "activity:tool-1", summary: "查询成功，返回 1 行。",
      artifact_ids: ["artifact_result"],
    });
  });

  it("projects a versioned dynamic plan into the product activity feed", () => {
    const next = reduceStreamEvent(state(), { kind: "event", event: {
      event_id: "event-plan", event_type: "plan.updated", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 1,
      timestamp: "2026-07-19T00:00:00Z", payload: { plan: {
        id: "plan-1", version: 2, status: "active", objective: "分析订单增长",
        summary: "趋势已确认，正在定位原因。",
        steps: [
          { id: "trend", title: "确认增长趋势", status: "completed", evidence_required: true, artifact_ids: ["artifact-result"] },
          { id: "cause", title: "定位异常原因", status: "in_progress", evidence_required: true, artifact_ids: [] },
        ],
      } },
    } });

    expect(next.detailById["session-1"].activities?.[0]).toMatchObject({
      id: "activity:plan:plan-1", kind: "plan", status: "running",
      current_step_id: "cause", artifact_ids: ["artifact-result"],
    });
  });

  it("projects cancelling and final answer product state without dropping structured sections", () => {
    const cancelling = reduceStreamEvent(state(), { kind: "event", event: {
      event_id: "event-cancelling", event_type: "run.cancelling", event_version: 1,
      session_id: "session-1", run_id: "run-1", sequence: 1,
      timestamp: "2026-07-19T00:00:00Z", payload: { run: { version: 2 } },
    } });
    expect(cancelling.runsById["run-1"]).toMatchObject({ status: "cancelling", cancel_requested: true, version: 2 });

    const answered = reduceStreamEvent(cancelling, { kind: "event", event: {
      event_id: "event-answer", event_type: "answer.completed", event_version: 1,
      session_id: "session-1", run_id: "run-1", sequence: 2,
      timestamp: "2026-07-19T00:00:01Z", payload: { response: {
        completion_disposition: "bounded_partial",
        limitation_codes: ["TURN_BUDGET_REACHED"],
        answer: {
        text: "订单增长。", evidence: [], key_findings: ["同比增长 12%"], caveats: ["样本有限"],
        recommendations: ["检查渠道"], follow_up_questions: ["是否按地区拆分？"],
      } } },
    } });
    expect(answered.runsById["run-1"].answer).toMatchObject({
      key_findings: ["同比增长 12%"], recommendations: ["检查渠道"],
      follow_up_questions: ["是否按地区拆分？"],
    });
    expect(answered.runsById["run-1"]).toMatchObject({
      completion_disposition: "bounded_partial",
      limitation_codes: ["TURN_BUDGET_REACHED"],
    });
  });

  it("settles active activities when cancellation becomes committed", () => {
    const initial = state();
    initial.detailById["session-1"].activities = [{
      id: "activity-running", run_id: "run-1", turn_id: "turn-1",
      kind: "analysis", title: "正在分析", status: "running",
    }];
    const cancelled = reduceStreamEvent(initial, { kind: "event", event: {
      event_id: "event-cancelled", event_type: "run.cancelled", event_version: 1,
      session_id: "session-1", run_id: "run-1", sequence: 1,
      timestamp: "2026-07-19T00:00:02Z", payload: { run: { version: 3 } },
    } });

    expect(cancelled.detailById["session-1"].activities?.[0]).toMatchObject({
      status: "cancelled", completed_at: "2026-07-19T00:00:02Z",
    });
  });

  it("applies Artifact updates to both normalized indexes", () => {
    const created = reduceStreamEvent(state(), { kind: "event", event: {
      event_id: "event-artifact-created", event_type: "artifact.created", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 1,
      timestamp: "2026-07-19T00:00:00Z", payload: { artifact: {
        id: "artifact-sql", run_id: "run-1", turn_id: "turn-1", type: "sql", title: "SQL",
        status: "creating", payload: { sql: "SELECT 1" }, relations: [],
      } },
    } });
    const updated = reduceStreamEvent(created, { kind: "event", event: {
      event_id: "event-artifact-updated", event_type: "artifact.updated", event_version: 1,
      session_id: "session-1", run_id: "run-1", turn_id: "turn-1", sequence: 2,
      timestamp: "2026-07-19T00:00:01Z", payload: { artifact: {
        id: "artifact-sql", run_id: "run-1", turn_id: "turn-1", type: "sql", title: "执行 SQL",
        status: "completed", payload: { sql: "SELECT 1" }, relations: [],
      } },
    } });
    expect(updated.artifactsById["artifact-sql"]).toMatchObject({ title: "执行 SQL", status: "completed" });
    expect(updated.detailById["session-1"].artifacts[0]).toBe(updated.artifactsById["artifact-sql"]);
  });
});
