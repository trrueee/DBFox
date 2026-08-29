import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AssistantMessageItem,
  ConversationArtifact,
  ConversationRun,
  ConversationRunItem,
  FunctionCallItem,
  FunctionCallOutputItem,
  PlanItem,
  UserMessageItem,
} from "../../../../types/conversation";
import { AgentTimeline } from "../AgentTimeline";
import { useDlcStore } from "../../../dlc/extensionStore";

const base = {
  session_id: "session-1",
  run_id: "run-1",
  turn_id: "turn-1",
  revision: 1,
  created_at: "2026-07-28T00:00:00Z",
} as const;

describe("AgentTimeline", () => {
  afterEach(() => {
    cleanup();
    useDlcStore.getState().reset();
  });

  it("accepts a distinct landmark name when multiple timelines share a page", () => {
    render(
      <AgentTimeline
        ariaLabel="流式回答时间线"
        run={run()}
        items={[]}
        artifacts={[]}
      />,
    );

    expect(screen.getByRole("region", { name: "流式回答时间线" })).toBeTruthy();
  });

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
    expect(screen.getByTitle("查找信息")).toBeTruthy();
    // Terminal tool rows are icon-only: no "已完成" word on the quiet row.
    expect(screen.queryByText("已完成")).toBeNull();
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
    expect(streamingArticle?.classList.contains("dbfox-message--assistant")).toBe(true);
    expect(streamingArticle?.querySelector(".conv-answer-document")).toBeTruthy();
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
    expect(completedArticle?.classList.contains("dbfox-message--assistant")).toBe(true);
    expect(completedArticle?.querySelector(".conv-answer-document")).toBeTruthy();
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

    const failureAlert = screen.getByRole("alert");
    expect(failureAlert.textContent).toContain("任务未完成，已有结果仍可使用");
    expect(failureAlert.textContent).toContain("本次分析未完成，请重试。");
    // Plan progress is the plan card's job — the outcome stays one line + a way back.
    expect(failureAlert.textContent).not.toContain("步骤完成");
    fireEvent.click(screen.getByRole("button", { name: "打开已保留工件：查询结果 result-1" }));
    expect(onSelectArtifact).toHaveBeenCalledWith("result-1");
    expect(screen.getByText("已保存结果")).toBeTruthy();
    expect(screen.queryByText("引用的数据来源")).toBeNull();
    fireEvent.click(screen.getByText("已保存结果").closest("summary")!);
    const savedPanel = screen.getByText("已保存结果").closest("details")!;
    fireEvent.click(within(savedPanel).getByText("查询结果 result-1"));
    expect(onSelectArtifact).toHaveBeenCalledWith("result-1");
  });

  it("coordinates failed Plan progress, blocked work, recovery, and safe technical details", () => {
    const failedPlan = planItem("result-1");
    failedPlan.status = "failed";
    failedPlan.payload.steps = [
      { id: "step-1", title: "读取订单", status: "completed", artifact_ids: ["result-1"] },
      { id: "step-2", title: "核对联盟渠道", status: "blocked", note: "缺少联盟渠道读取权限。" },
      { id: "step-3", title: "整理结论", status: "skipped" },
    ];

    renderTimeline(
      [failedPlan],
      {
        status: "failed",
        error: { code: "AGENT_RUNTIME_ERROR", message: "本次分析未完成，请调整权限后继续。" },
      },
      [resultArtifact("result-1")],
    );

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("任务未完成");
    expect(alert.textContent).toContain("本次分析未完成，请调整权限后继续。");
    // Blocked/skipped step detail lives in the plan checklist, not the outcome.
    expect(alert.textContent).not.toContain("受阻步骤");
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("AGENT_RUNTIME_ERROR")).toBeTruthy();
  });

  it("renders bounded partial as a non-destructive terminal outcome with preserved work", () => {
    const partialAnswer = assistant("当前结论仅覆盖已验证渠道。", "final_answer", 2);
    partialAnswer.payload.completion_disposition = "bounded_partial";
    partialAnswer.payload.limitation_codes = ["TOOL_BUDGET_REACHED", "INSUFFICIENT_EVIDENCE"];
    const partialPlan = planItem("result-1");
    partialPlan.payload.steps = [
      { id: "step-1", title: "读取订单", status: "completed", artifact_ids: ["result-1"] },
      { id: "step-2", title: "核对联盟渠道", status: "blocked" },
      { id: "step-3", title: "整理结论", status: "skipped" },
    ];

    const { container } = renderTimeline(
      [partialPlan, partialAnswer],
      { status: "completed" },
      [resultArtifact("result-1")],
    );

    const outcome = screen.getByText("分析部分完成，已有结果仍可使用").closest('[role="status"]')!;
    expect(outcome.textContent).toContain("分析部分完成，已有结果仍可使用");
    expect(outcome.textContent).toContain("停止原因：已达到工具调用上限；现有证据不足以完成全部判断。");
    expect(container.querySelector(".conv-completion-limitation")).toBeNull();
    expect(screen.queryByText("已完成当前可验证的工作")).toBeNull();
  });

  it("keeps cancellation neutral and explains that stopped steps do not resume", () => {
    renderTimeline(
      [],
      { status: "cancelled" },
      [resultArtifact("result-1")],
    );

    const outcome = screen.getByText("任务已停止，已有结果仍可使用").closest('[role="status"]')!;
    expect(outcome.textContent).toContain("任务已停止，已有结果仍可使用");
    expect(outcome.getAttribute("data-outcome")).toBe("cancelled");
  });

  it("shows only explicitly cited artifacts as data sources", () => {
    const answer = assistant("共有 42 条订单。", "final_answer", 1);
    answer.payload.evidence = [
      {
        id: "evidence-1",
        claim_id: "claim-1",
        artifact_id: "result-2",
        label: "共有 42 条订单",
        observed_at: "2026-08-15T00:00:00Z",
        locator: {},
      },
    ];

    renderTimeline(
      [answer],
      {},
      [resultArtifact("result-1"), resultArtifact("result-2")],
    );

    expect(screen.getByText("引用的数据来源")).toBeTruthy();
    fireEvent.click(screen.getByText("引用的数据来源").closest("summary")!);
    expect(screen.getByText("查询结果 result-2")).toBeTruthy();
    expect(screen.queryByText("查询结果 result-1")).toBeNull();
    expect(screen.queryByText("已保存结果")).toBeNull();
  });

  it("routes Plan step evidence through the existing artifact selection action", () => {
    const onSelectArtifact = vi.fn();
    const artifact = resultArtifact("result-1");
    renderTimeline([planItem("result-1")], {}, [artifact], onSelectArtifact);

    fireEvent.click(screen.getByRole("button", { name: /核对订单异常/ }));
    fireEvent.click(screen.getByRole("button", { name: `打开完成证据：${artifact.title}` }));

    expect(onSelectArtifact).toHaveBeenCalledWith("result-1");
  });

  it("groups consecutive function calls with the same title into a quiet group", () => {
    const call1 = call(1);
    const call2 = { ...call(2), id: "call-item-2", payload: { ...call(1).payload, call_id: "call-2" } };
    const call3 = { ...call(3), id: "call-item-3", payload: { ...call(1).payload, call_id: "call-3" } };

    renderTimeline([call1, call2, call3]);

    expect(screen.getByText("读取订单结构")).toBeTruthy();
    expect(screen.getByText(/3 次调用/)).toBeTruthy();
    expect(screen.queryByText(/2 次调用/)).toBeNull();
  });

  it("opens an in-progress tool disclosure so live status is not hidden", () => {
    const runningCall = call(1);
    runningCall.status = "in_progress";
    const { container } = renderTimeline([runningCall], { status: "running" });

    expect(screen.getByRole("button", { name: /读取订单结构/ }).getAttribute("aria-expanded")).toBe("true");
    // Live state is the spinner glyph itself, not a word.
    expect(container.querySelector(".animate-spin")).toBeTruthy();
    expect(screen.queryByText("运行中")).toBeNull();
  });

  it("renders a registered namespaced capability artifact in the conversation", () => {
    useDlcStore.getState().setProjectionResult("snapshot-1", {}, {
      connectors: [],
      dockViews: [],
      artifactViews: [{
        id: "dbfox.music.score",
        title: "乐谱",
        surfaces: ["inline", "workspace"],
        artifactTypes: [{ type: "dbfox.music.score_revision", schemaVersions: [1] }],
        parsePayload: (value) => value,
        render: (artifact) => <p>乐谱工件：{artifact.title}</p>,
      }],
    });
    const artifact: ConversationArtifact = {
      id: "score-artifact-1",
      session_id: "session-1",
      run_id: "run-1",
      version: 1,
      schema_version: 1,
      type: "dbfox.music.score_revision",
      title: "Warm Light",
      status: "completed",
      visibility: "primary",
      payload: { message: "score" },
      resource_refs: [],
      provenance: {},
      relations: [],
    };

    renderTimeline([], {}, [artifact]);

    expect(screen.getByText("乐谱工件：Warm Light")).toBeTruthy();
  });

  it("renders an embedded Artifact in the answer and omits the automatic duplicate", () => {
    useDlcStore.getState().setProjectionResult("snapshot-embed", {}, {
      connectors: [],
      dockViews: [],
      artifactViews: [{
        id: "dbfox.music.score",
        title: "乐谱",
        surfaces: ["inline", "workspace"],
        artifactTypes: [{ type: "dbfox.music.score_revision", schemaVersions: [1] }],
        parsePayload: (value) => value,
        render: (artifact) => <p>嵌入乐谱：{artifact.title}</p>,
      }],
    });
    const artifact: ConversationArtifact = {
      id: "artifact_score_1",
      session_id: "session-1",
      run_id: "run-1",
      version: 1,
      schema_version: 1,
      type: "dbfox.music.score_revision",
      title: "Warm Light",
      summary: null,
      payload: { scoreId: "score-1" },
      payload_ref: null,
      visibility: "primary",
      status: "completed",
      resource_refs: [],
      provenance: {},
      relations: [],
    };
    const answer = assistant(
      "先解释。\n\n{{artifact:artifact_score_1}}\n\n再总结。",
      "final_answer",
      1,
    );
    answer.payload.artifact_refs = [{ artifact_id: artifact.id }];

    renderTimeline([answer], { status: "completed" }, [artifact]);

    expect(screen.getByText("先解释。")).toBeTruthy();
    expect(screen.getByText("再总结。")).toBeTruthy();
    expect(screen.getAllByText("嵌入乐谱：Warm Light")).toHaveLength(1);
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
    type: "dbfox.data.result_view",
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

function planItem(artifactId: string): PlanItem {
  return {
    ...base,
    id: "plan-1",
    type: "plan",
    sequence: 1,
    status: "completed",
    payload: {
      objective: "核对订单异常",
      steps: [{
        id: "step-1",
        title: "核对查询结果",
        status: "completed",
        evidence_required: true,
        artifact_ids: [artifactId],
      }],
    },
  };
}

function run(): ConversationRun {
  return {
    id: "run-1",
    session_id: "session-1",
    input_id: "input-1",
    session_sequence: 1,
    user_message_id: "user-1",
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
