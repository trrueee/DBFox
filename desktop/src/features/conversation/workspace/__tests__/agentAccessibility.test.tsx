import axe from "axe-core";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentTimeline } from "../AgentTimeline";
import { ApprovalCard } from "../ApprovalCard";
import { QuestionCard } from "../QuestionCard";
import type {
  ApprovalItem,
  ConversationRun,
  FunctionCallItem,
  QuestionItem,
} from "../../../../types/conversation";

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
  it("keeps the dynamic function-call disclosure accessible", async () => {
    const tool: FunctionCallItem = {
      id: "tool-1",
      type: "function_call",
      session_id: "session-1",
      run_id: "run-1",
      turn_id: "turn-1",
      sequence: 1,
      revision: 1,
      status: "in_progress",
      created_at: "2026-07-26T00:00:00Z",
      payload: {
        call_id: "call-1",
        name: "sql_execute_readonly",
        tool_version: "1",
        presentation: {
          title: "执行只读查询",
          category: "query",
          visibility: "summary",
          progress: "indeterminate",
        },
        arguments: {},
        attempt: 1,
      },
    };
    const run: ConversationRun = {
      id: "run-1",
      session_id: "session-1",
      input_id: "input-1",
      session_sequence: 1,
      user_message_id: "user-1",
      datasource_id: "ds-1",
      question: "查询",
      status: "running",
      version: 1,
      cancel_requested: false,
      result: {},
      error: null,
    };
    const { container } = render(
      <AgentTimeline
        run={run}
        items={[tool]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );

    await expectNoAccessibilityViolations(container);
  });

  it("keeps approval decisions keyboard and screen-reader accessible", async () => {
    const approval: ApprovalItem = {
        id: "approval-1",
        type: "approval",
        run_id: "run-1",
        session_id: "session-1",
        turn_id: "turn-1",
        sequence: 1,
        revision: 1,
        status: "waiting",
        created_at: "2026-07-26T00:00:00Z",
        payload: {
          version: 0,
          risk_level: "warning",
          reason: "需要确认查询范围",
          requested_action: { sql: "SELECT 1" },
        },
      };
    const { container } = render(<ApprovalCard
      approval={approval}
      onOpenSqlConsole={vi.fn()}
      onResolve={vi.fn()}
    />);

    await expectNoAccessibilityViolations(container);
  });

  it("uses an accessible single-choice question interaction", async () => {
    const question: QuestionItem = {
        id: "question-1",
        type: "question",
        session_id: "session-1",
        run_id: "run-1",
        turn_id: "turn-1",
        sequence: 1,
        revision: 1,
        status: "waiting",
        created_at: "2026-07-26T00:00:00Z",
        payload: {
          version: 0,
          question: "使用哪个统计口径？",
          reason: "两个口径会产生不同结果",
          options: [
            { value: "calendar", label: "自然月" },
            { value: "fiscal", label: "财务月", description: "按照财务结算周期" },
          ],
          allow_free_text: true,
        },
      };
    const { container } = render(<QuestionCard
      question={question}
      onRespond={vi.fn()}
    />);

    await expectNoAccessibilityViolations(container);
  });
});
