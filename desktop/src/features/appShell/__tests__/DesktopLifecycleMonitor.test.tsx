import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { recoveryStatusMock } = vi.hoisted(() => ({
  recoveryStatusMock: vi.fn(),
}));

vi.mock("../../../lib/desktopHost", () => ({
  isEngineDesktopHost: () => true,
  getDesktopLaunchRecoveryStatus: recoveryStatusMock,
}));

import { DesktopLifecycleMonitor } from "../DesktopLifecycleMonitor";

describe("DesktopLifecycleMonitor", () => {
  beforeEach(() => {
    recoveryStatusMock.mockReset();
  });

  afterEach(cleanup);

  it("keeps crash recovery active without running the hidden update workflow", async () => {
    recoveryStatusMock.mockResolvedValue({ previousUncleanExit: true });
    const showToast = vi.fn();

    render(<DesktopLifecycleMonitor showToast={showToast} />);

    await waitFor(() => {
      expect(recoveryStatusMock).toHaveBeenCalledOnce();
      expect(showToast).toHaveBeenCalledWith(
        "检测到上次异常退出，已恢复安全的窗口与持久化工作区状态",
        "warning",
      );
    });
    expect(recoveryStatusMock).toHaveBeenCalledTimes(1);
  });
});
