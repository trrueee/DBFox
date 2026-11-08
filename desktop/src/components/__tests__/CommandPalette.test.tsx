import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPalette, type CommandItem } from "../CommandPalette";

function makeCommands(onRun = vi.fn()): CommandItem[] {
  return [
    {
      id: "open-sql",
      name: "打开 SQL 工作台",
      category: "工作区",
      shortcut: "Ctrl+K",
      action: onRun,
    },
    {
      id: "sync-schema",
      name: "同步表结构",
      category: "数据源",
      action: vi.fn(),
    },
  ];
}

describe("CommandPalette", () => {
  beforeAll(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => cleanup());

  it("renders commands with categories when open", () => {
    render(<CommandPalette open commands={makeCommands()} onClose={vi.fn()} />);

    expect(screen.getByRole("dialog", { name: "全局搜索" })).toBeTruthy();
    expect(screen.getByPlaceholderText("搜索任务、项目和操作…")).toBeTruthy();
    expect(screen.getByText("工作区")).toBeTruthy();
    expect(screen.getByText("打开 SQL 工作台")).toBeTruthy();
    expect(screen.getByText("同步表结构")).toBeTruthy();
  });

  it("runs a command and closes from cmdk selection", () => {
    const onRun = vi.fn();
    const onClose = vi.fn();
    render(<CommandPalette open commands={makeCommands(onRun)} onClose={onClose} />);

    fireEvent.click(screen.getByText("打开 SQL 工作台"));

    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape from the command input", () => {
    const onClose = vi.fn();
    render(<CommandPalette open commands={makeCommands()} onClose={onClose} />);

    fireEvent.keyDown(screen.getByPlaceholderText("搜索任务、项目和操作…"), { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps duplicate conversation titles as distinct cmdk items", () => {
    const duplicateCommands: CommandItem[] = [
      { id: "conversation-a", name: "hello", category: "最近对话", action: vi.fn() },
      { id: "conversation-b", name: "hello", category: "最近对话", action: vi.fn() },
    ];

    render(
      <CommandPalette open commands={duplicateCommands} onClose={vi.fn()} />,
    );

    expect(screen.getAllByText("hello")).toHaveLength(2);
    expect(document.querySelectorAll('[data-selected="true"]')).toHaveLength(1);
  });

  it.each([false, true])("returns focus after a programmatic open and Escape (conditional mount: %s)", async conditional => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return <><input aria-label="原输入框" /><button onClick={() => setOpen(true)}>打开搜索</button>
        {(!conditional || open) && <CommandPalette open={open} commands={makeCommands()} onClose={() => setOpen(false)} />}</>;
    }
    render(<Harness />);
    const caller = screen.getByRole("textbox", { name: "原输入框" });
    caller.focus();
    fireEvent.click(screen.getByRole("button", { name: "打开搜索" }));
    const search = screen.getByPlaceholderText("搜索任务、项目和操作…");
    await waitFor(() => expect(document.activeElement).toBe(search));
    fireEvent.keyDown(search, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(caller));
  });
});
