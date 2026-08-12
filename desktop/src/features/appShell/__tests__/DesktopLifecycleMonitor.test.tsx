import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock, isTauriMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  isTauriMock: vi.fn(() => true),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
  isTauri: isTauriMock,
}));

import { DesktopLifecycleMonitor } from "../DesktopLifecycleMonitor";

describe("DesktopLifecycleMonitor", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    isTauriMock.mockReset().mockReturnValue(true);
  });

  afterEach(cleanup);

  it("keeps crash recovery active without running the hidden update workflow", async () => {
    invokeMock.mockResolvedValue({ previousUncleanExit: true });
    const showToast = vi.fn();

    render(<DesktopLifecycleMonitor showToast={showToast} />);

    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith("get_launch_recovery_status");
      expect(showToast).toHaveBeenCalledWith(
        "检测到上次异常退出，已恢复安全的窗口与持久化工作区状态",
        "warning",
      );
    });
    expect(invokeMock).toHaveBeenCalledTimes(1);
  });
});
