import { describe, expect, it } from "vitest";
import type { ConversationRun } from "../../../../types/conversation";
import { buildRunTraceModel } from "../runTraceModel";

describe("runTraceModel", () => {
  it("uses the latest successful phase event instead of keeping running sticky", () => {
    const run: ConversationRun = {
      id: "run-1",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析订单",
      status: "completed",
      events: [
        {
          event_id: "validate-started",
          run_id: "run-1",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.step.started",
          step: {
            phase: "validating",
            tool_name: "sql.validate",
            status: "running",
            summary: "正在校验 SQL",
          },
        },
        {
          event_id: "validate-completed",
          run_id: "run-1",
          sequence: 2,
          created_at_ms: 2,
          type: "agent.step.completed",
          step: {
            phase: "validating",
            tool_name: "sql.validate",
            status: "completed",
            summary: "只读 SQL，可执行",
          },
        },
      ],
    };

    const model = buildRunTraceModel(run);

    expect(model.stages).toHaveLength(1);
    expect(model.stages[0]).toMatchObject({
      phase: "validating",
      status: "success",
      summary: "只读 SQL，可执行",
    });
  });

  it("keeps a failed phase failed even when later informational events arrive", () => {
    const run: ConversationRun = {
      id: "run-2",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析退款",
      status: "failed",
      events: [
        {
          event_id: "execute-failed",
          run_id: "run-2",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.step.failed",
          step: {
            phase: "executing",
            tool_name: "sql.execute_readonly",
            status: "failed",
            summary: "字段不存在",
          },
        },
        {
          event_id: "execute-observed",
          run_id: "run-2",
          sequence: 2,
          created_at_ms: 2,
          type: "agent.progress.update",
          step: {
            phase: "executing",
            status: "success",
            summary: "准备修复",
          },
        },
      ],
    };

    const model = buildRunTraceModel(run);

    expect(model.stages[0].status).toBe("failed");
    expect(model.stages[0].summary).toBe("准备修复");
  });

  it("archives dangling running phases when the run is completed", () => {
    const run: ConversationRun = {
      id: "run-3",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析注册用户",
      status: "completed",
      events: [
        {
          event_id: "repair-started",
          run_id: "run-3",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.progress.update",
          step: {
            phase: "repairing",
            name: "sql_repair",
            status: "running",
            summary: "Preparing SQL repair",
          },
        },
        {
          event_id: "run-completed",
          run_id: "run-3",
          sequence: 2,
          created_at_ms: 2,
          type: "agent.run.completed",
          step: { phase: "completed", status: "success", summary: "任务完成。" },
        },
      ],
    };

    const model = buildRunTraceModel(run);

    expect(model.stages.find((stage) => stage.phase === "repairing")?.status).toBe("success");
    expect(model.stages.find((stage) => stage.phase === "completed")?.status).toBe("success");
  });
});
