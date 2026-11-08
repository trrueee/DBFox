import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TitleBar from "../TitleBar";
import {
  closeDesktopWindow,
  getDesktopWindowMaximized,
  isEngineDesktopHost,
  minimizeDesktopWindow,
  subscribeDesktopWindowState,
  toggleMaximizeDesktopWindow,
} from "../../lib/desktopHost";

vi.mock("../../lib/desktopHost", () => ({
  closeDesktopWindow: vi.fn().mockResolvedValue(undefined),
  getDesktopWindowMaximized: vi.fn().mockResolvedValue(false),
  isEngineDesktopHost: vi.fn().mockReturnValue(true),
  minimizeDesktopWindow: vi.fn().mockResolvedValue(undefined),
  subscribeDesktopWindowState: vi.fn().mockReturnValue(() => {}),
  toggleMaximizeDesktopWindow: vi.fn().mockResolvedValue(true),
}));

describe("workspace window chrome", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(isEngineDesktopHost).mockReturnValue(true);
  });
  afterEach(cleanup);

  it("shows the current conversation once and follows native maximize state", async () => {
    render(<TitleBar title="分析最近一周的订单趋势" />);
    expect(screen.getByRole("heading", { name: "分析最近一周的订单趋势" })).toBeTruthy();
    expect(screen.queryByText("DBFox")).toBeNull();
    await waitFor(() => expect(subscribeDesktopWindowState).toHaveBeenCalledOnce());

    act(() => vi.mocked(subscribeDesktopWindowState).mock.calls[0][0](true));
    fireEvent.click(screen.getByRole("button", { name: "还原" }));
    expect(toggleMaximizeDesktopWindow).toHaveBeenCalledOnce();
  });

  it("keeps close and minimize independent from the header double-click action", async () => {
    render(<TitleBar />);
    await waitFor(() => expect(getDesktopWindowMaximized).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "最小化" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    fireEvent.doubleClick(screen.getByRole("button", { name: "关闭" }));
    expect(minimizeDesktopWindow).toHaveBeenCalledOnce();
    expect(closeDesktopWindow).toHaveBeenCalledOnce();
    expect(toggleMaximizeDesktopWindow).not.toHaveBeenCalled();
  });

  it("leaves new-task chrome free of a duplicate brand and browser window buttons", () => {
    vi.mocked(isEngineDesktopHost).mockReturnValue(false);
    render(<TitleBar />);
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(getDesktopWindowMaximized).not.toHaveBeenCalled();
  });

  it("releases the native listener when unmounted before the initial IPC read completes", async () => {
    let finish!: (value: boolean) => void;
    const unlisten = vi.fn();
    vi.mocked(getDesktopWindowMaximized).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    vi.mocked(subscribeDesktopWindowState).mockReturnValueOnce(unlisten);
    const view = render(<TitleBar />);
    view.unmount();
    expect(unlisten).toHaveBeenCalledOnce();
    await act(async () => finish(true));
    expect(subscribeDesktopWindowState).toHaveBeenCalledOnce();
  });

  it("does not overwrite a newer native event with a stale initial read", async () => {
    let finish!: (value: boolean) => void;
    vi.mocked(getDesktopWindowMaximized).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    render(<TitleBar />);
    act(() => vi.mocked(subscribeDesktopWindowState).mock.calls[0][0](true));
    await act(async () => finish(false));
    expect(screen.getByRole("button", { name: "还原" })).toBeTruthy();
  });
});
