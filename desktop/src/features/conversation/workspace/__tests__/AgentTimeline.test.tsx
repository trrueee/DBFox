import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AssistantMessageItem,
  ConversationArtifact,
  ConversationRun,
  ConversationRunItem,
  FunctionCallItem,
  FunctionCallOutputItem,
  UserMessageItem,
} from "../../../../types/conversation";
import { AgentTimeline } from "../AgentTimeline";

const base = {
  session_id: "session-1",
  run_id: "run-1",
  turn_id: "turn-1",
  revision: 1,
  created_at: "2026-07-28T00:00:00Z",
} as const;

describe("AgentTimeline", () => {
  afterEach(cleanup);
  it("keeps messages, calls, outputs, and the final answer in canonical sequence", () => {
    const items: ConversationRunItem[] = [
      user("检查订单", 1),
      assistant("我先检查订单表和相关字段。", "commentary", 2),
      call(3),
      output(4),
      assistant("订单表结构已确认，接下来汇总当前数据。", "commentary", 5, "turn-2"),
      assistant("共有 42 条订单。", "final_answer", 6, "turn-3"),
    ];

    const { container } = renderTimeline(items);
    const timelineText = container.querySelector(".conv-agent-timeline")?.textContent || "";
    expect(timelineText.indexOf("我先检查")).toBeLessThan(timelineText.indexOf("读取订单结构"));
    expect(timelineText.indexOf("读取订单结构")).toBeLessThan(timelineText.indexOf("结构已确认"));
    expect(timelineText.indexOf("结构已确认")).toBeLessThan(timelineText.indexOf("共有 42"));
  });

  it("reveals real function arguments and output without tool-name presentation mappings", () => {
    renderTimeline([call(1), output(2)]);

    fireEvent.click(screen.getByText("读取订单结构"));
    expect(screen.getByTitle("探索数据")).toBeTruthy();
    expect(screen.getByText("已完成")).toBeTruthy();
    expect(screen.getByText("schema_describe_table")).toBeTruthy();
    expect(screen.getByText(/orders/)).toBeTruthy();
    expect(screen.getByText("已读取 12 个字段")).toBeTruthy();
  });

  it("does not render a cancelled assistant message", () => {
    const cancelled = assistant("候选答案", "commentary", 1);
    cancelled.status = "cancelled";
    renderTimeline([cancelled]);
    expect(screen.queryByText("候选答案")).toBeNull();
  });

  it("renders a terminal answer when the provider omits phase", () => {
    const answer = assistant("这是最终答案。", null, 1);
    answer.payload.completion_disposition = "complete";
    const { container } = renderTimeline([answer]);

    expect(screen.getByText("这是最终答案。")).toBeTruthy();
    expect(container.querySelector(".conv-answer-document")).toBeTruthy();
  });

  it("keeps one presentation contract while an assistant message becomes terminal", () => {
    const streaming = assistant("## 分析结果\n\n订单保持增长。", null, 1);
    streaming.status = "in_progress";
    const { container, rerender } = renderTimeline([streaming], { status: "running" });

    const streamingArticle = container.querySelector(".conv-agent-message");
    expect(streamingArticle?.className).toBe("conv-agent-message conv-answer-document");
    expect(streamingArticle?.getAttribute("data-streaming-reveal")).toBe("true");

    const completed = {
      ...streaming,
      status: "completed" as const,
      payload: { ...streaming.payload, completion_disposition: "complete" as const },
    };
    rerender(
      <AgentTimeline
        run={{ ...run(), status: "completed" }}
        items={[completed]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onSelectArtifact={vi.fn()}
      />,
    );

    const completedArticle = container.querySelector(".conv-agent-message");
    expect(completedArticle?.className).toBe("conv-agent-message conv-answer-document");
    expect(completedArticle?.hasAttribute("data-streaming-reveal")).toBe(false);
    expect(screen.getByRole("heading", { name: "分析结果" })).toBeTruthy();
  });

  it("distinguishes a tool terminated by run failure from user cancellation", () => {
    const failedCall = call(1);
    failedCall.status = "cancelled";
    const failedOutput = output(2);
    failedOutput.status = "cancelled";
    renderTimeline([failedCall, failedOutput], {
      status: "failed",
      error: { code: "AGENT_RUNTIME_ERROR", message: "本次分析未完成，请重试。" },
    });

    expect(screen.getByText("因任务失败终止")).toBeTruthy();
    expect(screen.queryByText("已取消")).toBeNull();
  });

  it("keeps the cancelled label when the run was cancelled", () => {
    const cancelledCall = call(1);
    cancelledCall.status = "cancelled";
    const cancelledOutput = output(2);
    cancelledOutput.status = "cancelled";
    renderTimeline([cancelledCall, cancelledOutput], { status: "cancelled" });

    expect(screen.getByText("已取消")).toBeTruthy();
    expect(screen.queryByText("因任务失败终止")).toBeNull();
  });

  it("exposes completed query results when a later step fails", () => {
    const onSelectArtifact = vi.fn();
    renderTimeline(
      [call(1), output(2)],
      {
        status: "failed",
        error: { code: "AGENT_RUNTIME_ERROR", message: "本次分析未完成，请重试。" },
      },
      [resultArtifact("result-1"), resultArtifact("result-2"), resultArtifact("result-3")],
      onSelectArtifact,
    );

    expect(
      screen.getByText("分析未完成，但已保留 3 个查询结果，可在工件区查看。"),
    ).toBeTruthy();
    expect(screen.getByText("数据来源")).toBeTruthy();
    fireEvent.click(screen.getByText("查询结果 result-1"));
    expect(onSelectArtifact).toHaveBeenCalledWith("result-1");
  });
});

function renderTimeline(
  items: ConversationRunItem[],
  runOverride: Partial<ConversationRun> = {},
  artifacts: ConversationArtifact[] = [],
  onSelectArtifact = vi.fn(),
) {
  return render(
    <AgentTimeline
      run={{ ...run(), ...runOverride }}
      items={items}
      artifacts={artifacts}
      onOpenSqlConsole={vi.fn()}
      onSelectArtifact={onSelectArtifact}
    />,
  );
}

function resultArtifact(id: string): ConversationArtifact {
  return {
    id,
    session_id: "session-1",
    run_id: "run-1",
    turn_id: "turn-1",
    version: 1,
    type: "result_view",
    title: `查询结果 ${id}`,
    status: "completed",
    visibility: "primary",
    payload: {
      sourceSqlArtifactId: "sql-1",
      queryFingerprint: "fingerprint",
      datasourceGeneration: 1,
      columns: ["total"],
      rowCount: 1,
      returnedRows: 1,
      latencyMs: 1,
      executedAt: "2026-08-14T00:00:00Z",
      truncated: false,
    },
    provenance: {},
    relations: [],
  };
}

function run(): ConversationRun {
  return {
    id: "run-1",
    session_id: "session-1",
    input_id: "input-1",
    session_sequence: 1,
    user_message_id: "user-1",
    datasource_id: "ds-1",
    question: "检查订单",
    status: "completed",
    version: 3,
    cancel_requested: false,
    result: {},
    error: null,
  };
}

function user(content: string, sequence: number): UserMessageItem {
  return {
    ...base,
    id: "user-1",
    type: "message",
    sequence,
    status: "completed",
    payload: {
      role: "user",
      content,
      evidence: [],
      artifact_refs: [],
      limitation_codes: [],
    },
  };
}

function assistant(
  content: string,
  phase: "commentary" | "final_answer" | null,
  sequence: number,
  turnId = "turn-1",
): AssistantMessageItem {
  return {
    ...base,
    id: `message-${sequence}`,
    turn_id: turnId,
    type: "message",
    sequence,
    status: "completed",
    payload: {
      role: "assistant",
      phase,
      content,
      evidence: [],
      artifact_refs: [],
      limitation_codes: [],
      completion_disposition: phase === "final_answer" ? "complete" : null,
    },
  };
}

function call(sequence: number): FunctionCallItem {
  return {
    ...base,
    id: "call-item-1",
    type: "function_call",
    sequence,
    status: "completed",
    payload: {
      call_id: "call-1",
      name: "schema_describe_table",
      tool_version: "1",
      presentation: {
        title: "读取订单结构",
        category: "explore",
        visibility: "summary",
        progress: "indeterminate",
      },
      arguments: { table_name: "orders" },
      attempt: 1,
    },
  };
}

function output(sequence: number): FunctionCallOutputItem {
  return {
    ...base,
    id: "output-1",
    type: "function_call_output",
    sequence,
    status: "completed",
    payload: {
      call_id: "call-1",
      output: "{\"status\":\"succeeded\"}",
      summary: "已读取 12 个字段",
      artifact_refs: [],
    },
  };
}
