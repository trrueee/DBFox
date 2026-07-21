import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact, ConversationMessage, ConversationRun } from "../../../../types/conversation";
import { MessageList } from "../MessageList";

describe("MessageList", () => {
  beforeEach(() => {
    class ResizeObserverMock {
      private readonly callback: ResizeObserverCallback;
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
      }
      observe(target: Element) {
        this.callback([{ target, contentRect: target.getBoundingClientRect() } as ResizeObserverEntry], this);
      }
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
    HTMLElement.prototype.scrollTo = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get: () => 720 });
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 800 });
    HTMLElement.prototype.getBoundingClientRect = vi.fn(() => ({
      bottom: 720,
      height: 720,
      left: 0,
      right: 800,
      top: 0,
      width: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }));
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
          evidence: [{
            artifact_id: "sql_candidate",
            label: "SQL #1",
            query_fingerprint: "query-orders",
            observed_at: "2026-07-19T00:00:00Z",
          }],
          caveats: [],
          recommendations: [],
          follow_up_questions: [],
        },
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
      />,
    );

    expect(screen.getByRole("button", { name: "SQL: SQL" })).toBeTruthy();
  });

  it("scrolls when the latest message content grows during streaming", async () => {
    const scrollTo = vi.fn();
    HTMLElement.prototype.scrollTo = scrollTo;
    const baseMessage: ConversationMessage = {
      id: "assistant-stream",
      conversation_id: "conv-stream",
      role: "assistant",
      content: "Hel",
      status: "streaming",
      sequence: 1,
      created_at: null,
      updated_at: null,
    };

    const { rerender } = render(
      <MessageList
        messages={[baseMessage]}
        runs={[]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    await waitFor(() => expect(scrollTo).toHaveBeenCalledTimes(1));

    rerender(
      <MessageList
        messages={[{ ...baseMessage, content: "Hello" }]}
        runs={[]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    await waitFor(() => expect(scrollTo).toHaveBeenCalledTimes(2));
  });

  it("virtualizes long conversations while keeping stable message identities", async () => {
    const messages: ConversationMessage[] = Array.from({ length: 60 }, (_, index) => ({
      id: `message-${index + 1}`,
      conversation_id: "conv-long",
      role: index % 2 === 0 ? "user" : "assistant",
      content: `Message ${index + 1}`,
      status: "completed",
      sequence: index + 1,
      created_at: null,
      updated_at: null,
    }));

    const { container } = render(
      <MessageList
        messages={messages}
        runs={[]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(container.querySelector(".conv-message-column")?.classList.contains("is-virtualized")).toBe(true);
    await waitFor(() => {
      const virtualRows = container.querySelectorAll(".conv-message-virtual-row");
      expect(virtualRows.length).toBeGreaterThan(0);
      expect(virtualRows.length).toBeLessThan(messages.length);
      expect(virtualRows[0]?.getAttribute("data-index")).toBeTruthy();
    });
  });
});
