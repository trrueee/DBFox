import { afterEach, describe, expect, it, vi } from "vitest";

import type { DbfoxDesktopBridge, EngineStartupStatus } from "../../../shared/desktopContract";
import {
  getDesktopLaunchRecoveryStatus,
  getDesktopEngineConfig,
  getDesktopEngineStatus,
  isEngineDesktopHost,
  openDesktopDiagnosticLogs,
  pickDesktopFile,
  pickDesktopProjectFolder,
  readDesktopPickedFile,
  restartDesktopEngine,
  subscribeDesktopEngineState,
} from "../desktopHost";

afterEach(() => {
  delete window.dbfoxDesktop;
  vi.resetAllMocks();
});

describe("desktopHost engine boundary", () => {
  it("uses the Electron preload bridge as the only desktop runtime", async () => {
    const status: EngineStartupStatus = {
      state: "ready",
      error: null,
      stage: null,
      generation: 3,
      restartCount: 0,
    };
    const unsubscribe = vi.fn();
    const bridge: DbfoxDesktopBridge = {
      runtime: "electron",
      engine: {
        getConfig: vi.fn().mockResolvedValue({
          port: 18_625,
          token: "a".repeat(64),
          generation: 3,
          protocolVersion: 1,
          serverInfo: { name: "dbfox-engine", version: "test" },
          capabilities: ["http", "sse", "problem-details"],
        }),
        getStatus: vi.fn().mockResolvedValue(status),
        restart: vi.fn().mockResolvedValue(undefined),
        subscribe: vi.fn((listener) => {
          listener(status);
          return unsubscribe;
        }),
      },
      window: {
        isMaximized: vi.fn(), minimize: vi.fn(), toggleMaximize: vi.fn(), close: vi.fn(), subscribe: vi.fn(),
      },
      files: {
        pickProjectFolder: vi.fn(), pickFile: vi.fn(), readPickedFile: vi.fn(),
        listProjectFolder: vi.fn(), readProjectFile: vi.fn(),
        pickDlcPackage: vi.fn(), saveExternalImage: vi.fn(),
      },
      shell: { openExternalHttps: vi.fn(), openDiagnosticLogs: vi.fn() },
      diagnostics: { exportBundle: vi.fn() },
      lifecycle: { getRecoveryStatus: vi.fn() },
      updates: { getConfiguration: vi.fn(), check: vi.fn(), installPending: vi.fn() },
    };
    window.dbfoxDesktop = bridge;

    expect(isEngineDesktopHost()).toBe(true);
    vi.mocked(bridge.files.pickProjectFolder).mockResolvedValue("C:\\project");
    vi.mocked(bridge.files.pickFile).mockResolvedValue({
      path: "C:\\audio\\take.wav",
      name: "take.wav",
      sizeBytes: 32,
      modifiedAtUnix: 123,
    });
    vi.mocked(bridge.files.readPickedFile).mockResolvedValue(new Uint8Array([1, 2, 3]));
    vi.mocked(bridge.lifecycle.getRecoveryStatus).mockResolvedValue({ previousUncleanExit: false });
    expect((await getDesktopEngineConfig()).generation).toBe(3);
    expect(await getDesktopEngineStatus()).toEqual(status);
    expect(await pickDesktopProjectFolder()).toBe("C:\\project");
    expect(await pickDesktopFile({ filters: [{ name: "Audio", extensions: ["wav"] }] })).toMatchObject({ name: "take.wav" });
    expect(await readDesktopPickedFile("C:\\audio\\take.wav")).toEqual(new Uint8Array([1, 2, 3]));
    await openDesktopDiagnosticLogs();
    expect(await getDesktopLaunchRecoveryStatus()).toEqual({ previousUncleanExit: false });
    await restartDesktopEngine();
    const listener = vi.fn();
    expect(await subscribeDesktopEngineState(listener)).toBe(unsubscribe);
    expect(listener).toHaveBeenCalledWith(status);
    expect(bridge.shell.openDiagnosticLogs).toHaveBeenCalledOnce();
  });

  it("fails closed when the Electron preload bridge is absent", async () => {
    expect(isEngineDesktopHost()).toBe(false);
    await expect(getDesktopEngineConfig()).rejects.toThrow(
      "DBFox Electron preload bridge is unavailable",
    );
  });
});
