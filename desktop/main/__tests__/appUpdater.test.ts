import { describe, expect, it, vi } from "vitest";

import { AppUpdateService, type AppUpdaterAdapter } from "../appUpdater";

describe("Electron application updater boundary", () => {
  it("fails closed when the build has no signed update policy", async () => {
    const updater = fakeUpdater();
    const service = new AppUpdateService(updater, {
      configured: false,
      channel: "stable",
      currentVersion: "1.0.3",
      platformPolicy: "development",
    });

    await expect(service.check()).rejects.toThrow("未配置可验证");
    expect(updater.checkForUpdates).not.toHaveBeenCalled();
    expect(updater.autoDownload).toBe(false);
    expect(updater.autoInstallOnAppQuit).toBe(false);
    expect(updater.allowDowngrade).toBe(false);
    expect(updater.disableWebInstaller).toBe(true);
  });

  it("retains exactly the checked update before download and controlled install", async () => {
    const updater = fakeUpdater();
    vi.mocked(updater.checkForUpdates).mockResolvedValue({
      isUpdateAvailable: true,
      updateInfo: {
        version: "1.0.4",
        releaseNotes: "Security update",
        releaseDate: "2026-08-21T00:00:00Z",
      },
    });
    const service = new AppUpdateService(updater, {
      configured: true,
      channel: "stable",
      currentVersion: "1.0.3",
      platformPolicy: "code-signed",
    });

    expect(await service.check()).toEqual({
      available: true,
      currentVersion: "1.0.3",
      version: "1.0.4",
      body: "Security update",
      publishedAtUnix: 1_787_270_400,
    });
    expect((await service.check()).version).toBe("1.0.4");
    expect(updater.checkForUpdates).toHaveBeenCalledOnce();
    const prepare = vi.fn().mockResolvedValue(undefined);
    await service.installPending(prepare);
    expect(updater.downloadUpdate).toHaveBeenCalledOnce();
    expect(prepare).toHaveBeenCalledOnce();
    expect(updater.quitAndInstall).toHaveBeenCalledWith(false, true);
  });

  it("does not stop the running application when update download fails", async () => {
    const updater = fakeUpdater();
    vi.mocked(updater.checkForUpdates).mockResolvedValue({
      isUpdateAvailable: true,
      updateInfo: { version: "1.0.4" },
    });
    vi.mocked(updater.downloadUpdate).mockRejectedValue(new Error("signature mismatch"));
    const service = new AppUpdateService(updater, {
      configured: true,
      channel: "stable",
      currentVersion: "1.0.3",
      platformPolicy: "code-signed",
    });
    await service.check();
    const prepare = vi.fn();
    await expect(service.installPending(prepare)).rejects.toThrow("无法完成更新操作");
    expect(prepare).not.toHaveBeenCalled();
    expect(updater.quitAndInstall).not.toHaveBeenCalled();
  });
});

function fakeUpdater(): AppUpdaterAdapter {
  return {
    autoDownload: true,
    autoInstallOnAppQuit: true,
    allowPrerelease: true,
    allowDowngrade: true,
    disableWebInstaller: false,
    checkForUpdates: vi.fn().mockResolvedValue(null),
    downloadUpdate: vi.fn().mockResolvedValue([]),
    quitAndInstall: vi.fn(),
  };
}
