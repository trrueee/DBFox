import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAppCommands } from "../useAppCommands";

describe("useAppCommands", () => {
  it("includes an appearance settings command", () => {
    const openSettings = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        conversations: [],
        showSmartQueryHome: vi.fn(),
        showProjectOverview: vi.fn(),
        openConversation: vi.fn(),
        openSettings,
      }),
    );

    const command = result.current.commandItems.find((item) => item.id === "appearance-settings");
    expect(command?.name).toBe("外观与字号设置");
    command?.action();
    expect(openSettings).toHaveBeenCalledWith("appearance");
  });

  it("includes a diagnostics log command", () => {
    const openSettings = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        conversations: [],
        showSmartQueryHome: vi.fn(),
        showProjectOverview: vi.fn(),
        openConversation: vi.fn(),
        openSettings,
      }),
    );

    const command = result.current.commandItems.find((item) => item.id === "diagnostics-logs");

    expect(command?.name).toBe("系统诊断");
    expect(command?.category).toBe("设置");
    command?.action();
    expect(openSettings).toHaveBeenCalledWith("diagnostics");
  });

  it("does not expose the unfinished update settings surface", () => {
    const openSettings = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        conversations: [],
        showSmartQueryHome: vi.fn(),
        showProjectOverview: vi.fn(),
        openConversation: vi.fn(),
        openSettings,
      }),
    );

    expect(result.current.commandItems.find((item) => item.id === "updates-settings")).toBeUndefined();
    expect(openSettings).not.toHaveBeenCalled();
  });

  it("does not expose Data-specific commands from Core composition", () => {
    const { result } = renderHook(() =>
      useAppCommands({
        conversations: [],
        showSmartQueryHome: vi.fn(),
        showProjectOverview: vi.fn(),
        openConversation: vi.fn(),
        openSettings: vi.fn(),
      }),
    );

    expect(result.current.commandItems.find((item) => item.id === "connection-manager")).toBeUndefined();
    expect(result.current.commandItems.find((item) => item.id === "create-datasource")).toBeUndefined();
    expect(result.current.commandItems.find((item) => item.id === "new-sql")).toBeUndefined();
  });

  it("routes project management through the Core-owned project overview and drops the context command", () => {
    const showProjectOverview = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        conversations: [],
        showSmartQueryHome: vi.fn(),
        showProjectOverview,
        openConversation: vi.fn(),
        openSettings: vi.fn(),
      }),
    );

    expect(result.current.commandItems.find((item) => item.id === "add-context")).toBeUndefined();
    const command = result.current.commandItems.find((item) => item.id === "project-context");
    expect(command?.name).toBe("项目管理");
    command?.action();
    expect(showProjectOverview).toHaveBeenCalledOnce();
  });
});
