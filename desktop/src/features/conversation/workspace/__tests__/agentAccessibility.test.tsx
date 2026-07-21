import axe from "axe-core";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActivityFeed } from "../ActivityFeed";
import { ApprovalCard } from "../ApprovalCard";
import { QuestionCard } from "../QuestionCard";

async function expectNoAccessibilityViolations(container: HTMLElement) {
  const result = await axe.run(container, {
    rules: {
      // jsdom has no layout/paint engine; contrast is covered by visual token tests.
      "color-contrast": { enabled: false },
    },
  });
  expect(result.violations.map((violation) => ({
    id: violation.id,
    targets: violation.nodes.flatMap((node) => node.target),
  }))).toEqual([]);
}

describe("Agent workspace accessibility", () => {
  it("keeps the dynamic Activity disclosure accessible", async () => {
    const { container } = render(<ActivityFeed activities={[{
      id: "activity-1",
      run_id: "run-1",
      turn_id: "turn-1",
      kind: "tool",
      title: "执行只读查询",
      summary: "已返回结果工件",
      status: "running",
    }]} />);

    await expectNoAccessibilityViolations(container);
  });

  it("keeps approval decisions keyboard and screen-reader accessible", async () => {
    const { container } = render(<ApprovalCard
      runId="run-1"
      approval={{
        id: "approval-1",
        run_id: "run-1",
        session_id: "session-1",
        tool_name: "sql.execute_readonly",
        status: "pending",
        risk_level: "warning",
        reason: "需要确认查询范围",
        requested_action: { sql: "SELECT 1" },
      }}
      onOpenSqlConsole={vi.fn()}
      onResolve={vi.fn()}
    />);

    await expectNoAccessibilityViolations(container);
  });

  it("uses an accessible single-choice question interaction", async () => {
    const { container } = render(<QuestionCard
      question={{
        id: "question-1",
        run_id: "run-1",
        turn_id: "turn-1",
        status: "pending",
        version: 0,
        question: "使用哪个统计口径？",
        reason: "两个口径会产生不同结果",
        options: [
          { value: "calendar", label: "自然月" },
          { value: "fiscal", label: "财务月", description: "按照财务结算周期" },
        ],
        allow_free_text: true,
      }}
      onRespond={vi.fn()}
    />);

    await expectNoAccessibilityViolations(container);
  });
});
