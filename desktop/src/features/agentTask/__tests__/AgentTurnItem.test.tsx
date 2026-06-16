import { act, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentTurnItem } from "../AgentTurnItem";
import type { ConversationTurn } from "../types";

function completedTurn(): ConversationTurn {
  return {
    id: "turn-1",
    userMessage: "分析一下用户使用小红书工具的详率",
    hasAgentData: true,
    agentStatus: "completed",
    agentTimeline: [
      {
        id: "tool-db-query",
        kind: "tool",
        title: "db.query",
        status: "success",
        toolName: "db.query",
        output: { rows: [], rowCount: 0 },
        latencyMs: 120,
      },
    ],
    agentAnswer: {
      answer: "查询完成。",
      key_findings: [],
      evidence: [],
      caveats: [],
      recommendations: [],
      follow_up_questions: [],
    },
  };
}

describe("AgentTurnItem", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("keeps the trace open after the user expands a completed turn", () => {
    render(
      <AgentTurnItem
        turn={completedTurn()}
        isLast
        onOpenSqlConsole={vi.fn()}
        onSendFollowUp={vi.fn()}
        onToast={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /已完成/ }));
    expect(screen.getByText("收起思考过程")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(700);
    });

    expect(screen.getByText("收起思考过程")).toBeInTheDocument();
  });
});
