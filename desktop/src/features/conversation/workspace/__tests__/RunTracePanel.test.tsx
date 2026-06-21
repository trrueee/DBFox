import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ConversationRun } from "../../../../types/conversation";
import { RunTracePanel } from "../RunTracePanel";

describe("RunTracePanel", () => {
  it("renders persisted runtime events as an execution timeline", () => {
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
          type: "agent.step.completed",
          step: {
            name: "tools",
            tool_name: "sql.execute_readonly",
            status: "completed",
            summary: "查询完成",
          },
        },
      ],
    };

    render(<RunTracePanel run={run} />);

    expect(screen.getByText("sql.execute_readonly")).toBeTruthy();
    expect(screen.getByText("查询完成")).toBeTruthy();
  });
});
