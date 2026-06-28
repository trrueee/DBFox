import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
      requested_action: { args: { safe_sql: "SELECT * FROM orders" } },
      created_at: "2026-06-22T00:00:00Z",
    },
    events: [],
  };
}

describe("MessageBubble", () => {
  beforeEach(() => {
    cleanup();
  });

  afterEach(() => {
    vi.useRealTimers();
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

  it("renders a read-only approval audit card for resolved approvals", () => {
    const run = approvalRun();
    run.status = "completed";
    run.approval = {
      ...run.approval!,
      status: "approved",
      decided_at: "2026-06-22T02:30:00Z",
      decided_by: "local-user",
      decision_note: "确认只读执行",
    };

    render(
      <MessageBubble
        message={{ ...assistantMessage, content: "查询已继续。", status: "completed" }}
        run={run}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByText("审批已批准")).toBeTruthy();
    expect(screen.getByText("决定人：local-user")).toBeTruthy();
    expect(screen.getByText("审批时间：2026-06-22 02:30:00 UTC")).toBeTruthy();
    expect(screen.getByText("确认只读执行")).toBeTruthy();
    expect(screen.getByText("SELECT * FROM orders")).toBeTruthy();
  });

  it("renders clickable evidence chips for grounded answers", () => {
    const onOpenSqlConsole = vi.fn();
    const onSelectArtifact = vi.fn();
    render(
      <MessageBubble
        message={{ ...assistantMessage, content: "订单查询完成。", status: "completed" }}
        run={{
          id: "run-evidence",
          conversation_id: "conv-approval",
          datasource_id: "ds-1",
          question: "orders",
          assistant_message_id: "assistant-approval",
          status: "completed",
          answer: {
            answer: "订单查询完成。",
            key_findings: [],
            evidence: [{ artifact_id: "sql_candidate", label: "SQL #1" }],
            caveats: [],
            recommendations: [],
            follow_up_questions: [],
          },
          events: [],
        }}
        artifacts={[
          {
            id: "artifact-sql",
            semantic_id: "sql_candidate",
            conversation_id: "conv-approval",
            run_id: "run-evidence",
            message_id: "assistant-approval",
            type: "sql",
            title: "SQL",
            status: "completed",
            payload: { sql: "SELECT id FROM orders" },
            depends_on: [],
          },
        ]}
        onOpenSqlConsole={onOpenSqlConsole}
        onOpenResultTab={vi.fn()}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "SQL #1" }));

    expect(onOpenSqlConsole).toHaveBeenCalledWith("SELECT id FROM orders");
    expect(onSelectArtifact).toHaveBeenCalledWith("artifact-sql");
  });

  it("marks answers without result evidence as schema-only", () => {
    render(
      <MessageBubble
        message={{ ...assistantMessage, content: "可能和 orders 表有关。", status: "completed" }}
        run={{
          id: "run-schema-only",
          conversation_id: "conv-approval",
          datasource_id: "ds-1",
          question: "orders",
          assistant_message_id: "assistant-approval",
          status: "completed",
          answer: {
            answer: "可能和 orders 表有关。",
            key_findings: [],
            evidence: [],
            caveats: [],
            recommendations: [],
            follow_up_questions: [],
          },
          events: [],
        }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByText("未执行查询，仅基于 schema 推断")).toBeTruthy();
  });

  it("reveals streaming assistant text progressively when a large delta lands", async () => {
    vi.useFakeTimers();
    const longAnswer = "这是一个较长的流式回答片段，用来模拟模型在很短时间内吐出一整段内容。";
    const { rerender } = render(
      <MessageBubble
        message={{ ...assistantMessage, content: "", status: "streaming" }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByText("Thinking...")).toBeTruthy();

    rerender(
      <MessageBubble
        message={{ ...assistantMessage, content: longAnswer, status: "streaming" }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.queryByText(longAnswer)).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60);
    });

    expect(screen.getByText(/这是一个/)).toBeTruthy();
    expect(screen.queryByText(longAnswer)).toBeNull();

    for (let i = 0; i < 80; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
    }

    expect(screen.getByText(longAnswer)).toBeTruthy();
  });

  it("renders completed assistant text immediately without typewriter smoothing", () => {
    const completedAnswer = "历史消息应该直接完整显示。";

    render(
      <MessageBubble
        message={{ ...assistantMessage, content: completedAnswer, status: "completed" }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByText(completedAnswer)).toBeTruthy();
  });

  it("renders table cell markdown cleanly inside assistant answers", () => {
    render(
      <MessageBubble
        message={{
          ...assistantMessage,
          status: "completed",
          content: [
            "| 维度 | DBFox | 普通 AI |",
            "| --- | --- | --- |",
            "| **SQL 能力** | 自动验证 `sql.validate`<br>执行只读查询 | 只能给示例 SQL |",
          ].join("\n"),
        }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByText("SQL 能力")).toBeTruthy();
    expect(screen.getByText("sql.validate")).toBeTruthy();
    expect(screen.getByText("执行只读查询")).toBeTruthy();
    expect(screen.queryByText(/\*\*SQL 能力\*\*/)).toBeNull();
    expect(screen.queryByText(/<br>/)).toBeNull();
  });
});
