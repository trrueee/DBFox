import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { configurationMock, recoveryMock, checkMock, installMock } = vi.hoisted(() => ({
  configurationMock: vi.fn(),
  recoveryMock: vi.fn(),
  checkMock: vi.fn(),
  installMock: vi.fn(),
}));

vi.mock("../../../lib/desktopHost", () => ({
  isEngineDesktopHost: () => true,
  getDesktopUpdateConfiguration: configurationMock,
  getDesktopLaunchRecoveryStatus: recoveryMock,
  checkForDesktopUpdate: checkMock,
  installPendingDesktopUpdate: installMock,
}));

import { UpdateSettingsPanel } from "../UpdateSettingsPanel";

describe("UpdateSettingsPanel", () => {
  beforeEach(() => {
    configurationMock.mockReset();
    recoveryMock.mockReset();
    checkMock.mockReset();
    installMock.mockReset();
  });

  afterEach(cleanup);

  it("makes an unsigned development build explicit and disables checks", async () => {
    configurationMock.mockResolvedValue({
      configured: false, channel: "stable", currentVersion: "1.0.3", platformPolicy: "development",
    });
    recoveryMock.mockResolvedValue({ previousUncleanExit: false });

    render(<UpdateSettingsPanel showToast={vi.fn()} />);

    expect(await screen.findByText("此构建未启用自动更新")).toBeTruthy();
    expect(screen.getByRole("button", { name: "检查更新" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("上次会话正常结束")).toBeTruthy();
  });

  it("checks and installs only the update retained by the Electron boundary", async () => {
    const showToast = vi.fn();
    configurationMock.mockResolvedValue({
      configured: true, channel: "stable", currentVersion: "1.0.3", platformPolicy: "code-signed",
    });
    recoveryMock.mockResolvedValue({ previousUncleanExit: true });
    checkMock.mockResolvedValue({
      available: true,
      currentVersion: "1.0.3",
      version: "1.0.4",
      body: "安全与稳定性更新",
      publishedAtUnix: null,
    });
    installMock.mockResolvedValue(undefined);

    render(<UpdateSettingsPanel showToast={showToast} />);

    await screen.findByText("代码签名更新通道已启用");
    expect(screen.getByText("检测到上次异常退出")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "检查更新" }));
    expect(await screen.findByText("DBFox 1.0.4")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "下载、验证并安装" }));

    await waitFor(() => expect(installMock).toHaveBeenCalledOnce());
    expect(showToast).toHaveBeenCalledWith("发现 DBFox 1.0.4", "info");
  });
});
