import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAppCommands } from "../useAppCommands";

describe("useAppCommands", () => {
  it("includes an appearance settings command", () => {
    const openSettings = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        tables: [],
        conversations: [],
        openSqlConsole: vi.fn(),
        showSmartQueryHome: vi.fn(),
        openConversation: vi.fn(),
        openSettings,
        openConnectionDialog: vi.fn(),
        openTable: vi.fn(),
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
        tables: [],
        conversations: [],
        openSqlConsole: vi.fn(),
        showSmartQueryHome: vi.fn(),
        openConversation: vi.fn(),
        openSettings,
        openConnectionDialog: vi.fn(),
        openTable: vi.fn(),
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
        tables: [],
        conversations: [],
        openSqlConsole: vi.fn(),
        showSmartQueryHome: vi.fn(),
        openConversation: vi.fn(),
        openSettings,
        openConnectionDialog: vi.fn(),
        openTable: vi.fn(),
      }),
    );

    expect(result.current.commandItems.find((item) => item.id === "updates-settings")).toBeUndefined();
    expect(openSettings).not.toHaveBeenCalled();
  });

  it("omits the legacy connection manager when Data DLC owns the connector", () => {
    const openConnectionDialog = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        tables: [],
        conversations: [],
        openSqlConsole: vi.fn(),
        showSmartQueryHome: vi.fn(),
        openConversation: vi.fn(),
        openSettings: vi.fn(),
        openConnectionDialog,
        connectionManagementAvailable: false,
        openTable: vi.fn(),
      }),
    );

    expect(result.current.commandItems.find((item) => item.id === "connection-manager")).toBeUndefined();
    result.current.commandItems.find((item) => item.id === "create-datasource")?.action();
    expect(openConnectionDialog).toHaveBeenCalledWith("create");
  });
});
