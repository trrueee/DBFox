import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationMessage, ConversationRun } from "../../../../types/conversation";
import { MessageBubble } from "../MessageBubble";

const assistantMessage: ConversationMessage = {
  id: "assistant-approval",
  conversation_id: "conv-approval",
  role: "assistant",
  content: "需要确认后继续。",
  status: "streaming",
  sequence: 1,
  created_at: null,
  updated_at: null,
};

function approvalRun(): ConversationRun {
  return {
    id: "run-approval",
    conversation_id: "conv-approval",
    datasource_id: "ds-1",
    question: "orders",
    assistant_message_id: "assistant-approval",
    status: "waiting_approval",
    approval: {
      id: "approval-1",
      run_id: "run-approval",
      session_id: "conv-approval",
      step_name: "sql.execute_readonly",
      tool_name: "sql.execute_readonly",
      status: "pending",
      risk_level: "warning",
      reason: "生产环境需要确认",
      policy_decision: {},
      requested_action: { args: { sql: "SELECT * FROM orders" } },
      created_at: "2026-06-22T00:00:00Z",
    },
    events: [],
  };
}

describe("MessageBubble", () => {
  beforeEach(() => {
    cleanup();
  });

  it("renders an approval card for pending approvals", () => {
    const onResolveApproval = vi.fn();
    render(
      <MessageBubble
        message={assistantMessage}
        run={approvalRun()}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
        onResolveApproval={onResolveApproval}
      />,
    );

    expect(screen.getByText("需要审批")).toBeTruthy();
    expect(screen.getByText("风险级别：warning")).toBeTruthy();
    expect(screen.getByText("生产环境需要确认")).toBeTruthy();
    expect(screen.getByText("SELECT * FROM orders")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "批准执行" }));
    expect(onResolveApproval).toHaveBeenCalledWith("run-approval", "approval-1", true);

    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    expect(onResolveApproval).toHaveBeenCalledWith("run-approval", "approval-1", false);
  });
});
