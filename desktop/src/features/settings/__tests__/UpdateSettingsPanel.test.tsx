import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock, isTauriMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  isTauriMock: vi.fn(() => true),
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
  isTauri: isTauriMock,
}));

import { UpdateSettingsPanel } from "../UpdateSettingsPanel";

describe("UpdateSettingsPanel", () => {
  beforeEach(() => {
    invokeMock.mockReset();
    isTauriMock.mockReset().mockReturnValue(true);
  });

  afterEach(cleanup);

  it("makes an unsigned development build explicit and disables checks", async () => {
    invokeMock.mockImplementation((command: string) => {
      if (command === "get_update_configuration") {
        return Promise.resolve({ configured: false, channel: "stable", currentVersion: "1.0.3" });
      }
      if (command === "get_launch_recovery_status") {
        return Promise.resolve({ previousUncleanExit: false });
      }
      return Promise.reject(new Error(`unexpected command ${command}`));
    });

    render(<UpdateSettingsPanel showToast={vi.fn()} />);

    expect(await screen.findByText("此构建未启用自动更新")).toBeTruthy();
    expect(screen.getByRole("button", { name: "检查更新" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("上次会话正常结束")).toBeTruthy();
  });

  it("checks and installs only the update retained by the Rust boundary", async () => {
    const showToast = vi.fn();
    invokeMock.mockImplementation((command: string) => {
      if (command === "get_update_configuration") {
        return Promise.resolve({ configured: true, channel: "stable", currentVersion: "1.0.3" });
      }
      if (command === "get_launch_recovery_status") {
        return Promise.resolve({ previousUncleanExit: true });
      }
      if (command === "check_for_app_update") {
        return Promise.resolve({
          available: true,
          currentVersion: "1.0.3",
          version: "1.0.4",
          body: "安全与稳定性更新",
          publishedAtUnix: null,
        });
      }
      if (command === "install_pending_app_update") return Promise.resolve();
      return Promise.reject(new Error(`unexpected command ${command}`));
    });

    render(<UpdateSettingsPanel showToast={showToast} />);

    await screen.findByText("签名更新通道已启用");
    expect(screen.getByText("检测到上次异常退出")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "检查更新" }));
    expect(await screen.findByText("DBFox 1.0.4")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "下载、验证并安装" }));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith("install_pending_app_update"));
    expect(showToast).toHaveBeenCalledWith("发现 DBFox 1.0.4", "info");
  });
});
