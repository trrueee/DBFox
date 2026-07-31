import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAppCommands } from "../useAppCommands";

describe("useAppCommands", () => {
  it("includes a diagnostics log command", () => {
    const openSettings = vi.fn();
    const { result } = renderHook(() =>
      useAppCommands({
        tables: [],
        conversations: [],
        openSqlConsole: vi.fn(),
        openSmartQueryTab: vi.fn(),
        openConversationHistoryTab: vi.fn(),
        openConversationResult: vi.fn(),
        openSettings,
        openConnectionManagerTab: vi.fn(),
        openNewConnectionTab: vi.fn(),
        openTableTab: vi.fn(),
      }),
    );

    const command = result.current.commandItems.find((item) => item.id === "diagnostics-logs");

    expect(command?.name).toBe("系统诊断");
    expect(command?.category).toBe("设置");
    command?.action();
    expect(openSettings).toHaveBeenCalledWith("diagnostics");
  });
});
