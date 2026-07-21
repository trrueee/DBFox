import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

    expect(screen.getByPlaceholderText("输入指令或搜索表、字段、功能…")).toBeTruthy();
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

    fireEvent.keyDown(screen.getByPlaceholderText("输入指令或搜索表、字段、功能…"), { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
