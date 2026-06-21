import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAppCommands } from "../useAppCommands";

describe("useAppCommands", () => {
  it("includes a diagnostics log command", () => {
    const openDiagnosticsTab = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        tables: [],
        tableColumns: {},
        openSqlConsole: vi.fn(),
        openSmartQueryTab: vi.fn(),
        openConversationHistoryTab: vi.fn(),
        openLlmConfigTab: vi.fn(),
        openConnectionManagerTab: vi.fn(),
        openNewConnectionTab: vi.fn(),
        openAgentEvalTab: vi.fn(),
        openDiagnosticsTab,
        openTableTab: vi.fn(),
      }),
    );

    const command = result.current.commandItems.find((item) => item.id === "diagnostics-logs");

    expect(command?.name).toBe("打开诊断日志");
    expect(command?.category).toBe("开发与诊断");
    command?.action();
    expect(openDiagnosticsTab).toHaveBeenCalledOnce();
  });
});
