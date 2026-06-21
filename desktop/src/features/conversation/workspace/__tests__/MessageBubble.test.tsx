import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConversationMessage, ConversationRun } from "../../../../types/conversation";
import { MessageBubble } from "../MessageBubble";

describe("MessageBubble", () => {
  it("renders assistant answers as document content with the trace above the answer", () => {
    const message: ConversationMessage = {
      id: "assistant-1",
      conversation_id: "conv-1",
      role: "assistant",
      content: "## 用户注册数据分析报告\n\n这里是正文。",
      status: "completed",
      sequence: 2,
      created_at: null,
      updated_at: null,
    };
    const run: ConversationRun = {
      id: "run-1",
      conversation_id: "conv-1",
      datasource_id: "ds-1",
      question: "分析用户注册的数据",
      status: "completed",
      assistant_message_id: message.id,
      events: [
        {
          event_id: "evt-1",
          run_id: "run-1",
          sequence: 1,
          created_at_ms: 1,
          type: "agent.run.completed",
          step: { name: "progress", summary: "Run completed" },
        },
      ],
    };

    const { container } = render(
      <MessageBubble message={message} run={run} artifacts={[]} onOpenSqlConsole={vi.fn()} />,
    );

    const article = container.querySelector(".conv-message");
    const trace = container.querySelector(".conv-run-trace");
    const answerTitle = screen.getByText("用户注册数据分析报告");

    expect(article?.classList.contains("conv-message-answer")).toBe(true);
    expect(trace).toBeTruthy();
    expect(trace!.compareDocumentPosition(answerTitle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
