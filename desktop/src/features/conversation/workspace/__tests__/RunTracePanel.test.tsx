import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { ConversationRun } from "../../../../types/conversation";
import { RunTracePanel } from "../RunTracePanel";

describe("RunTracePanel", () => {
  beforeEach(() => {
    cleanup();
  });

  it("groups runtime events into a compact stage timeline", () => {
    const run: ConversationRun = {
      id: "run-stage",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析订单趋势",
      status: "completed",
      events: [
        {
          event_id: "evt-understanding",
          run_id: "run-stage",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.progress.update",
          step: {
            name: "model",
            phase: "understanding",
            status: "success",
            summary: "理解问题并准备检索相关表。",
          },
        },
        {
          event_id: "evt-search",
          run_id: "run-stage",
          sequence: 2,
          created_at_ms: 2,
          type: "agent.step.completed",
          step: {
            name: "搜索相关表和字段",
            tool_name: "db.search",
            phase: "searching_schema",
            status: "success",
            summary: "命中 orders 和 users。",
          },
        },
        {
          event_id: "evt-validate",
          run_id: "run-stage",
          sequence: 3,
          created_at_ms: 3,
          type: "agent.step.completed",
          step: {
            name: "校验 SQL 安全性",
            tool_name: "sql.validate",
            phase: "validating",
            status: "success",
            summary: "只读 SQL，可执行。",
          },
        },
        {
          event_id: "evt-execute",
          run_id: "run-stage",
          sequence: 4,
          created_at_ms: 4,
          type: "agent.step.completed",
          step: {
            name: "执行只读查询",
            tool_name: "sql.execute_readonly",
            phase: "executing",
            status: "success",
            summary: "查询返回 128 行。",
            rowCount: 128,
            durationMs: 42,
          },
        },
        {
          event_id: "evt-answer",
          run_id: "run-stage",
          sequence: 5,
          created_at_ms: 5,
          type: "agent.answer.completed",
          step: {
            name: "answer",
            phase: "synthesizing",
            status: "success",
            summary: "整理最终答案。",
          },
        },
        {
          event_id: "evt-completed",
          run_id: "run-stage",
          sequence: 6,
          created_at_ms: 6,
          type: "agent.run.completed",
          step: {
            name: "completed",
            phase: "completed",
            status: "success",
            summary: "任务完成。",
          },
        },
      ],
    };

    const { container } = render(<RunTracePanel run={run} />);

    expect(screen.getByText("执行过程 · 6 阶段 · 1 条 SQL · 128 行 · 42ms")).toBeTruthy();
    expect(screen.getByText("理解问题")).toBeTruthy();
    expect(screen.getByText("搜索结构")).toBeTruthy();
    expect(screen.getByText("安全校验")).toBeTruthy();
    expect(screen.getByText("执行查询")).toBeTruthy();
    expect(screen.getByText("整理回答")).toBeTruthy();
    expect(screen.getByText("完成")).toBeTruthy();
    expect(container.querySelectorAll(".conv-run-stage")).toHaveLength(6);
    expect(container.textContent).not.toContain("Run ID:");
    expect(container.textContent).not.toContain("sql.execute_readonly");
  });

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

    expect(screen.getByText("执行过程 · 1 阶段 · 1 条 SQL · 128 行 · 42ms")).toBeTruthy();
    expect(screen.getByText("执行只读查询")).toBeTruthy();
    expect(screen.getAllByText("查询返回 128 行，正在整理结论。").length).toBeGreaterThan(0);
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

  it("shows memory and semantic references from context updates", () => {
    const run: ConversationRun = {
      id: "run-context",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析新注册用户 GMV",
      status: "running",
      events: [
        {
          event_id: "evt-context",
          run_id: "run-context",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.context.update",
          step: {
            summary: "Using semantic context",
            task_lens: {
              memory_references: [
                {
                  label: "GMV definition",
                  summary: "GMV = paid_amount - refund_amount",
                  source: "memory",
                },
              ],
              semantic_references: [
                {
                  label: "新注册用户",
                  summary: "users.created_at",
                  source: "db",
                },
              ],
            },
          },
        },
      ],
    };

    render(<RunTracePanel run={run} />);

    expect(screen.getByText("参考业务记忆")).toBeTruthy();
    expect(screen.getByText("GMV definition")).toBeTruthy();
    expect(screen.getByText("GMV = paid_amount - refund_amount")).toBeTruthy();
    expect(screen.getByText("字段理解")).toBeTruthy();
    expect(screen.getByText("新注册用户")).toBeTruthy();
    expect(screen.getByText("users.created_at")).toBeTruthy();
  });

  it("shows SQL repair root cause and recovery strategy outside debug details", () => {
    const run: ConversationRun = {
      id: "run-repair",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析退款金额",
      status: "running",
      events: [
        {
          event_id: "evt-repair",
          run_id: "run-repair",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.progress.update",
          step: {
            name: "sql_repair",
            phase: "repairing",
            status: "running",
            summary: "Column not found — looking up schema to fix the query.",
            error_class: "missing_column",
            root_cause: "column refund_amount not found in orders",
            recovery_strategy: "Use schema.describe_table and fuzzy-match similar columns, then sql.revise.",
            attempt: 1,
          },
        },
      ],
    };

    render(<RunTracePanel run={run} />);

    expect(screen.getByText("SQL 修复")).toBeTruthy();
    expect(screen.getByText("missing_column")).toBeTruthy();
    expect(screen.getByText("第 1 次修复")).toBeTruthy();
    expect(screen.getByText("column refund_amount not found in orders")).toBeTruthy();
    expect(screen.getByText("Use schema.describe_table and fuzzy-match similar columns, then sql.revise.")).toBeTruthy();
  });
});
