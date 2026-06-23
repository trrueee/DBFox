import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../../types/conversation";
import { MessageList } from "../MessageList";

describe("MessageList", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollTo = vi.fn();
    cleanup();
  });

  it("attaches runs and artifacts to the addressed assistant message", () => {
    const messages: ConversationMessage[] = [
      {
        id: "user-1",
        conversation_id: "conv-1",
        role: "user",
        content: "分析订单",
        status: "completed",
        sequence: 1,
        created_at: null,
        updated_at: null,
      },
      {
        id: "assistant-1",
        conversation_id: "conv-1",
        role: "assistant",
        content: "订单查询完成。",
        status: "completed",
        sequence: 2,
        created_at: null,
        updated_at: null,
      },
    ];
    const runs: ConversationRun[] = [
      {
        id: "run-1",
        conversation_id: "conv-1",
        datasource_id: "ds-1",
        question: "分析订单",
        assistant_message_id: "assistant-1",
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
      },
    ];
    const artifacts: ConversationArtifact[] = [
      {
        id: "artifact-sql",
        semantic_id: "sql_candidate",
        conversation_id: "conv-1",
        run_id: "run-1",
        message_id: "assistant-1",
        type: "sql",
        title: "SQL",
        status: "completed",
        payload: { sql: "SELECT id FROM orders" },
        depends_on: [],
      },
    ];

    render(
      <MessageList
        messages={messages}
        runs={runs}
        artifacts={artifacts}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
        onResolveApproval={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "SQL #1" })).toBeTruthy();
  });
});
