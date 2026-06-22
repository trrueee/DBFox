import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ConversationRun } from "../../../../types/conversation";
import { RunTracePanel } from "../RunTracePanel";

describe("RunTracePanel", () => {
  it("renders completed runtime events with product labels and a compact summary", () => {
    const run: ConversationRun = {
      id: "run-1",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析用户注册的数据",
      status: "completed",
      events: [
        {
          event_id: "evt-1",
          run_id: "run-1",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.tool.completed",
          step: {
            name: "tools",
            tool_name: "sql.execute_readonly",
            status: "completed",
            summary: "查询返回 128 行，正在整理结论。",
            rowCount: 128,
            durationMs: 42,
          },
        },
      ],
    };

    const { container } = render(<RunTracePanel run={run} />);

    expect(screen.getByText("执行过程 · 1 步 · 1 条 SQL · 128 行 · 42ms")).toBeTruthy();
    expect(screen.getByText("执行只读查询")).toBeTruthy();
    expect(screen.getByText("查询返回 128 行，正在整理结论。")).toBeTruthy();
    expect(screen.queryByText("sql.execute_readonly")).toBeNull();
    expect(container.querySelector("details")?.hasAttribute("open")).toBe(false);
  });

  it("keeps failed traces open with the failure reason visible", () => {
    const run: ConversationRun = {
      id: "run-2",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析订单",
      status: "failed",
      error_message: "SQL 语法错误",
      events: [
        {
          event_id: "evt-1",
          run_id: "run-2",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.run.failed",
          error: "SQL 语法错误",
        },
      ],
    };

    const { container } = render(<RunTracePanel run={run} />);

    expect(screen.getAllByText("执行失败").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SQL 语法错误").length).toBeGreaterThan(0);
    expect(container.querySelector("details")?.hasAttribute("open")).toBe(true);
  });
});
