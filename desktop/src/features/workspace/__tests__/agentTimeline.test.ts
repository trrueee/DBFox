import { describe, expect, it } from "vitest";
import { appendAgentRuntimeEvent, createInitialAgentTimeline, timelineFromFinalResponse } from "../agentTimeline";
import type { AgentRunResponse, AgentRuntimeEvent } from "../../../lib/api/types";

function event(overrides: Partial<AgentRuntimeEvent>): AgentRuntimeEvent {
  return {
    event_id: overrides.event_id || `evt-${overrides.sequence || 1}`,
    run_id: "run-1",
    sequence: overrides.sequence || 1,
    created_at_ms: 1,
    type: overrides.type || "agent.step.started",
    ...overrides,
  };
}

describe("agentTimeline", () => {
  it("merges tool started and completed events into a LangSmith-like tool node", () => {
    let timeline = createInitialAgentTimeline("分析用户使用平台的数据");

    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 2,
      type: "agent.step.started",
      step: { name: "search_database", tool_name: "db.search", input: { query: "用户 使用 平台" } },
    }));
    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 3,
      type: "agent.step.completed",
      step: {
        name: "search_database",
        tool_name: "db.search",
        status: "success",
        latency_ms: 42,
        output: { total_matches: 20 },
      },
    }));

    expect(timeline).toHaveLength(2);
    expect(timeline[1]).toMatchObject({
      id: "tool-db.search-2",
      kind: "tool",
      title: "db.search",
      subtitle: "search_database",
      status: "success",
      input: { query: "用户 使用 平台" },
      output: { total_matches: 20 },
      latencyMs: 42,
    });
  });

  it("keeps repeated tool invocations separate so stale errors do not pollute later successes", () => {
    let timeline = createInitialAgentTimeline("analyze feature usage");

    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 2,
      type: "agent.step.completed",
      step: {
        name: "query_database",
        tool_name: "db.query",
        status: "failed",
        input: { sql: "SELECT bad_column FROM audit_logs" },
        error: "TrustGate blocked execution because schema validation found unknown tables or columns.",
        latency_ms: 11,
      },
    }));
    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 3,
      type: "agent.step.completed",
      step: {
        name: "query_database",
        tool_name: "db.query",
        status: "success",
        input: { sql: "SELECT COUNT(*) AS total_logs FROM audit_logs" },
        output: { rows: [{ total_logs: "3024" }] },
        latency_ms: 12,
      },
    }));

    const toolItems = timeline.filter((item) => item.kind === "tool");
    expect(toolItems).toHaveLength(2);
    expect(toolItems[0]).toMatchObject({
      status: "failed",
      error: "TrustGate blocked execution because schema validation found unknown tables or columns.",
    });
    expect(toolItems[1]).toMatchObject({
      status: "success",
      output: { rows: [{ total_logs: "3024" }] },
      error: null,
    });
  });

  it("hydrates final response steps with input, output, and answer", () => {
    const response: AgentRunResponse = {
      run_id: "run-1",
      session_id: "session-1",
      success: true,
      status: "completed",
      question: "分析用户使用平台的数据",
      artifacts: [],
      steps: [{
        name: "db.inspect",
        status: "success",
        latency_ms: 8,
        input: { target: "account_behaviors" },
        output: { name: "account_behaviors", columns: [{ name: "action_type" }] },
      }],
      answer: {
        answer: "account_behaviors: 6 column(s)",
        key_findings: [],
        evidence: [],
        caveats: [],
        recommendations: [],
        follow_up_questions: [],
      },
    };

    const timeline = timelineFromFinalResponse(createInitialAgentTimeline(response.question), response);

    expect(timeline.map((item) => item.id)).toEqual(["user-request", "tool-db.inspect", "agent-answer"]);
    expect(timeline[1].input).toEqual({ target: "account_behaviors" });
    expect(timeline[1].output).toEqual({ name: "account_behaviors", columns: [{ name: "action_type" }] });
    expect(timeline[2].content).toBe("account_behaviors: 6 column(s)");
  });

  it("hydrates final mapped steps into existing live tool nodes", () => {
    let timeline = createInitialAgentTimeline("搜索用户表");
    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 2,
      type: "agent.step.started",
      step: { name: "search_database", tool_name: "db.search", input: { query: "用户" } },
    }));

    const response: AgentRunResponse = {
      run_id: "run-1",
      session_id: "session-1",
      success: true,
      status: "completed",
      question: "搜索用户表",
      artifacts: [],
      steps: [{
        name: "search_database",
        status: "success",
        latency_ms: 12,
        input: { query: "用户" },
        output: { total_matches: 3 },
      }],
    };

    timeline = timelineFromFinalResponse(timeline, response);

    expect(timeline.filter((item) => item.kind === "tool")).toHaveLength(1);
    expect(timeline[1]).toMatchObject({
      id: "tool-db.search-2",
      title: "db.search",
      subtitle: "search_database",
      output: { total_matches: 3 },
    });
  });

  it("filters boilerplate progress and normalizes recovery updates", () => {
    let timeline = createInitialAgentTimeline("数据库的表里有哪些ai工具");

    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 2,
      type: "agent.progress.update",
      step: {
        status: "running",
        summary: "Tool observation received; continuing ReAct loop.",
      },
    }));
    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 3,
      type: "agent.progress.update",
      step: {
        status: "running",
        summary: "Tool observation received; continuing ReAct loop.",
      },
    }));
    timeline = appendAgentRuntimeEvent(timeline, event({
      sequence: 4,
      type: "agent.progress.update",
      step: {
        status: "running",
        summary: "Use schema.describe_table and fuzzy-match similar columns, then sql.revise.",
      },
    }));

    expect(timeline.filter((item) => item.kind === "assistant").map((item) => item.content)).toEqual([
      "正在查找相近字段并修正查询。",
    ]);
  });
});
