import { describe, expect, it } from "vitest";
import { parseConversationTurns } from "../types";
import type { WorkspaceTab } from "../../../types/workspace";

function baseTab(overrides: Partial<WorkspaceTab>): WorkspaceTab {
  return {
    id: "tab-1",
    title: "问数结果",
    type: "query-result",
    ...overrides,
  };
}

describe("parseConversationTurns", () => {
  it("does not render an agent final answer again as plain aiText", () => {
    const turns = parseConversationTurns(
      baseTab({
        chatMessages: [
          { id: 1, sender: "user", text: "分析小红书工具使用情况" },
          { id: 2, sender: "ai", text: "The result contains 14 profiled rows." },
        ],
        agentStatus: "completed",
        agentTimeline: [
          {
            id: "answer",
            kind: "tool",
            title: "answer.synthesize",
            status: "success",
            toolName: "answer.synthesize",
          },
        ],
        agentAnswer: {
          answer: "已完成查询，共返回 14 行结果。",
          key_findings: [],
          evidence: [],
          caveats: [],
          recommendations: [],
          follow_up_questions: [],
        },
      }),
    );

    expect(turns).toHaveLength(1);
    expect(turns[0].hasAgentData).toBe(true);
    expect(turns[0].agentAnswer?.answer).toBe("已完成查询，共返回 14 行结果。");
    expect(turns[0].aiText).toBeUndefined();
  });
});
