import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    vi.unstubAllGlobals();
  });
  it("leaves readers in place until they choose to return to the latest output", async () => {
    const scrollTo = vi.fn();
    const { container, rerender } = render(<MessageList runs={[run("run-1", 1)]} items={[user("run-1", 1), answer("run-1", 1)]} artifacts={[]} />);
    const viewport = container.querySelector(".conv-message-scroll") as HTMLDivElement;
    viewport.scrollTo = scrollTo;
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, value: 1800 },
      clientHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    fireEvent.scroll(viewport);
    expect(screen.getByRole("button", { name: "回到最新" })).toBeTruthy();
    rerender(<MessageList runs={[run("run-1", 1)]} items={[user("run-1", 1), { ...answer("run-1", 1), revision: 2, payload: { ...answer("run-1", 1).payload, content: "追加的真实输出" } }]} artifacts={[]} />);
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    expect(scrollTo).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "回到最新" }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 1800, behavior: "auto" });
    expect(screen.queryByRole("button", { name: "回到最新" })).toBeNull();
  });

  it("removes the jump control when a larger viewport already contains the latest output", () => {
    const resize = new Set<() => void>();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: ResizeObserverCallback) { resize.add(() => callback([], this as unknown as ResizeObserver)); }
      observe() {} unobserve() {} disconnect() {}
    });
    const { container } = render(<MessageList runs={[run("run-1", 1)]} items={[answer("run-1", 1)]} artifacts={[]} />);
    const viewport = container.querySelector(".conv-message-scroll") as HTMLDivElement;
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, value: 1800 },
      clientHeight: { configurable: true, value: 500 },
      scrollTop: { configurable: true, writable: true, value: 0 },
    });
    fireEvent.scroll(viewport);
    expect(screen.getByRole("button", { name: "回到最新" })).toBeTruthy();
    Object.defineProperty(viewport, "scrollHeight", { configurable: true, value: 480 });
    act(() => resize.forEach(callback => callback()));
    expect(screen.queryByRole("button", { name: "回到最新" })).toBeNull();
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
    const { rerender } = render(
      <MessageList
        runs={[queued]}
        items={[user("run-queued", 1)]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );
    expect(screen.getByText("问题 1")).toBeTruthy();
    expect(screen.getByText("已排队")).toBeTruthy();
    expect(screen.getByText("当前任务结束后将自动开始")).toBeTruthy();
    expect(screen.queryByText("正在等待模型响应")).toBeNull();

    rerender(
      <MessageList
        runs={[{ ...queued, status: "running", phase: "waiting_model" }]}
        items={[user("run-queued", 1)]}
        artifacts={[]}
        onOpenSqlConsole={vi.fn()}
      />,
    );
    expect(screen.queryByText("已排队")).toBeNull();
    expect(screen.getByText("正在处理")).toBeTruthy();
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
    expect(screen.getByText("正在准备操作")).toBeTruthy();
    expect(screen.queryByText("模型正在生成结构化参数")).toBeNull();
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
