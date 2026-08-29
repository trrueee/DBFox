import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AssistantMessageItem,
  ConversationRun,
  UserMessageItem,
} from "../../../../types/conversation";
import { MessageList } from "../MessageList";

function run(id: string, sequence: number): ConversationRun {
  return {
    id,
    session_id: "session-1",
    input_id: `input-${sequence}`,
    session_sequence: sequence,
    user_message_id: `user-${sequence}`,
    question: `问题 ${sequence}`,
    status: "completed",
    version: 1,
    cancel_requested: false,
    result: {},
    error: null,
  };
}

function user(runId: string, sequence: number): UserMessageItem {
  return {
    id: `user-${sequence}`,
    type: "message",
    session_id: "session-1",
    run_id: runId,
    sequence: sequence * 2 - 1,
    revision: 1,
    status: "completed",
    created_at: `2026-07-26T00:00:0${sequence}Z`,
    payload: {
      role: "user",
      content: `问题 ${sequence}`,
      evidence: [],
      artifact_refs: [],
      limitation_codes: [],
    },
  };
}

function answer(runId: string, sequence: number): AssistantMessageItem {
  return {
    id: `message-${sequence}`,
    type: "message",
    session_id: "session-1",
    run_id: runId,
    turn_id: `turn-${sequence}`,
    sequence: sequence * 2,
    revision: 1,
    status: "completed",
    created_at: `2026-07-26T00:00:0${sequence}Z`,
    completed_at: `2026-07-26T00:01:0${sequence}Z`,
    payload: {
      role: "assistant",
      phase: "final_answer",
      content: `回答 ${sequence}`,
      evidence: [],
      artifact_refs: [],
      completion_disposition: "complete",
      limitation_codes: [],
    },
  };
}

describe("MessageList", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  it("projects each run's user input and answer without cross-run leakage", () => {
    const runs = [run("run-1", 1), run("run-2", 2)];
    render(
      <MessageList
        runs={runs}
        items={[
          user("run-1", 1),
          answer("run-1", 1),
          user("run-2", 2),
          answer("run-2", 2),
        ]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );
    expect(screen.getByText("问题 1")).toBeTruthy();
    expect(screen.getByText("回答 1")).toBeTruthy();
    expect(screen.getByText("问题 2")).toBeTruthy();
    expect(screen.getByText("回答 2")).toBeTruthy();
  });

  it("shows the user question immediately while a run is queued", () => {
    const queued = run("run-queued", 1);
    queued.status = "queued";
    render(
      <MessageList
        runs={[queued]}
        items={[user("run-queued", 1)]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );
    expect(screen.getByText("问题 1")).toBeTruthy();
    expect(screen.getByText("正在等待模型响应")).toBeTruthy();
  });

  it("shows the provider-neutral phase while structured tool arguments are prepared", () => {
    const active = run("run-preparing", 1);
    active.status = "running";
    active.phase = "preparing_tool_call";
    render(
      <MessageList
        runs={[active]}
        items={[user("run-preparing", 1)]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );
    expect(screen.getByText("正在准备工具调用")).toBeTruthy();
    expect(screen.getByText("模型正在生成结构化参数")).toBeTruthy();
  });

  it("exposes bounded history loading, pending, exhausted, and retry states", async () => {
    const onLoadOlderHistory = vi.fn().mockResolvedValue(false);
    const { rerender } = render(
      <MessageList
        runs={[run("run-2", 2)]}
        items={[user("run-2", 2), answer("run-2", 2)]}
        artifacts={[]}
        hasOlderHistory
        onLoadOlderHistory={onLoadOlderHistory}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "载入更早消息" }));
    expect(onLoadOlderHistory).toHaveBeenCalledOnce();

    rerender(
      <MessageList
        runs={[run("run-2", 2)]}
        items={[user("run-2", 2), answer("run-2", 2)]}
        artifacts={[]}
        hasOlderHistory
        loadingOlderHistory
        onLoadOlderHistory={onLoadOlderHistory}
      />,
    );
    expect(screen.getByRole("button", { name: "正在载入更早消息…" })).toHaveProperty(
      "disabled",
      true,
    );

    rerender(
      <MessageList
        runs={[run("run-1", 1), run("run-2", 2)]}
        items={[
          user("run-1", 1),
          answer("run-1", 1),
          user("run-2", 2),
          answer("run-2", 2),
        ]}
        artifacts={[]}
        olderHistoryLoaded
        onLoadOlderHistory={onLoadOlderHistory}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("已载入全部消息");

    rerender(
      <MessageList
        runs={[run("run-1", 1), run("run-2", 2)]}
        items={[
          user("run-1", 1),
          answer("run-1", 1),
          user("run-2", 2),
          answer("run-2", 2),
        ]}
        artifacts={[]}
        hasOlderHistory
        historyLoadError="网络连接中断"
        onLoadOlderHistory={onLoadOlderHistory}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain("网络连接中断");
    expect(screen.getByRole("button", { name: "重试载入更早消息" })).toBeTruthy();
  });

  it("virtualizes long conversation history by Run instead of mounting every timeline", async () => {
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(800);
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(720);
    const runs = Array.from({ length: 80 }, (_, index) => run(`run-${index + 1}`, index + 1));
    const items = runs.flatMap((item, index) => [
      user(item.id, index + 1),
      answer(item.id, index + 1),
    ]);
    const { container } = render(
      <MessageList
        runs={runs}
        items={items}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );

    const column = container.querySelector(".conv-message-column");
    expect(column?.classList.contains("is-virtualized")).toBe(true);
    await waitFor(() => {
      const mountedRuns = container.querySelectorAll(".conv-message-virtual-row");
      expect(mountedRuns.length).toBeGreaterThan(0);
      expect(mountedRuns.length).toBeLessThan(runs.length);
    });
    expect(column?.getAttribute("data-virtual-layout")).toMatch(/^messages-/);
  });
});
