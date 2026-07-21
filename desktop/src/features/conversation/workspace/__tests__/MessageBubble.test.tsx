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
      requested_action: { arguments: { sql: "SELECT * FROM orders" } },
      created_at: "2026-06-22T00:00:00Z",
    },
  };
}

describe("MessageBubble", () => {
  beforeEach(() => {
    cleanup();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not duplicate the composer-pinned approval inside a message", () => {
    render(
      <MessageBubble
        message={assistantMessage}
        run={approvalRun()}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.queryByText("需要你的批准")).toBeNull();
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

    expect(screen.getByText("已确认")).toBeTruthy();
    expect(screen.getByText("处理人：local-user")).toBeTruthy();
    expect(screen.getByText((content) => content.startsWith("批准时间："))).toBeTruthy();
    expect(screen.getByText("确认只读执行")).toBeTruthy();
    expect(screen.getByText("SELECT * FROM orders")).toBeTruthy();
  });

  it("renders inline evidence references for grounded claims", () => {
    const onOpenSqlConsole = vi.fn();
    const onSelectArtifact = vi.fn();
    render(
      <MessageBubble
        message={{ ...assistantMessage, content: "订单共有 42 条。{{cite:artifact_result}}", status: "completed" }}
        run={{
          id: "run-evidence",
          conversation_id: "conv-approval",
          datasource_id: "ds-1",
          question: "orders",
          assistant_message_id: "assistant-approval",
          status: "completed",
          answer: {
            answer: "订单共有 42 条。{{cite:artifact_result}}",
            key_findings: [],
            evidence: [{
              artifact_id: "artifact_result",
              label: "订单统计结果",
              query_fingerprint: "query-orders",
              observed_at: "2026-07-19T00:00:00Z",
            }],
            caveats: [],
            recommendations: [],
            follow_up_questions: [],
          },
        }}
        artifacts={[
          {
            id: "artifact_result",
            semantic_id: "result_view",
            conversation_id: "conv-approval",
            run_id: "run-evidence",
            message_id: "assistant-approval",
            type: "result_view",
            title: "订单统计结果",
            status: "completed",
            payload: { rowCount: 1, columns: ["count"] },
            depends_on: [],
          },
        ]}
        onOpenSqlConsole={onOpenSqlConsole}
        onOpenResultTab={vi.fn()}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看证据：订单统计结果" }));

    expect(onOpenSqlConsole).not.toHaveBeenCalled();
    expect(onSelectArtifact).toHaveBeenCalledWith("artifact_result");
  });

  it("does not append a misleading schema-only note to direct answers", () => {
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
        }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.queryByText("未执行查询，仅根据表结构推断")).toBeNull();
  });

  it("renders bounded completion from the public completion contract", () => {
    render(
      <MessageBubble
        message={{ ...assistantMessage, content: "这是当前可验证的结果。", status: "completed" }}
        run={{
          id: "run-partial",
          conversation_id: "conv-approval",
          datasource_id: "ds-1",
          question: "分析订单",
          assistant_message_id: "assistant-approval",
          status: "completed",
          completion_disposition: "bounded_partial",
          limitation_codes: ["TURN_BUDGET_REACHED"],
          answer: { answer: "这是当前可验证的结果。", evidence: [] },
        }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );

    expect(screen.getByText("已完成当前可验证的分析")).toBeTruthy();
    expect(screen.getByText("已达到分析轮次上限")).toBeTruthy();
  });

  it("shows cancellation as a retained product state", () => {
    render(
      <MessageBubble
        message={{ ...assistantMessage, content: "", status: "cancelled" }}
        run={{
          id: "run-cancelled",
          conversation_id: "conv-approval",
          datasource_id: "ds-1",
          question: "停止分析",
          assistant_message_id: "assistant-approval",
          status: "cancelled",
        }}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );

    expect(screen.getByText("任务已停止")).toBeTruthy();
    expect(screen.getByText(/已产生的分析步骤和工件仍然保留/)).toBeTruthy();
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

    expect(screen.getByText("正在分析问题…")).toBeTruthy();

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
    const sqlCapabilityCell = screen.getByText("sql.validate").closest("td");
    if (!sqlCapabilityCell) throw new Error("Expected SQL capability table cell");
    expect(sqlCapabilityCell.querySelector("br")).toBeTruthy();
    expect(screen.queryByText(/\*\*SQL 能力\*\*/)).toBeNull();
    expect(screen.queryByText(/<br>/)).toBeNull();
  });
});
