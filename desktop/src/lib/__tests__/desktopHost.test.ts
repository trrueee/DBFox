import { afterEach, describe, expect, it, vi } from "vitest";

import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import type { DbfoxDesktopBridge, EngineStartupStatus } from "../../../shared/desktopContract";
import {
  getDesktopLaunchRecoveryStatus,
  getDesktopEngineConfig,
  getDesktopEngineStatus,
  isEngineDesktopHost,
  openDesktopDiagnosticLogs,
  pickDesktopProjectFolder,
  restartDesktopEngine,
  subscribeDesktopEngineState,
} from "../desktopHost";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  isTauri: vi.fn(),
}));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));

const mockInvoke = vi.mocked(invoke);
const mockIsTauri = vi.mocked(isTauri);
const mockListen = vi.mocked(listen);

afterEach(() => {
  delete window.dbfoxDesktop;
  vi.resetAllMocks();
});

describe("desktopHost engine boundary", () => {
  it("uses the Electron preload bridge without invoking the Tauri runtime", async () => {
    mockIsTauri.mockReturnValue(false);
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
        pickProjectFolder: vi.fn(), listProjectFolder: vi.fn(), readProjectFile: vi.fn(),
        pickDlcPackage: vi.fn(), saveExternalImage: vi.fn(),
      },
      shell: { openExternalHttps: vi.fn(), openDiagnosticLogs: vi.fn() },
      diagnostics: { exportBundle: vi.fn() },
      lifecycle: { getRecoveryStatus: vi.fn() },
    };
    window.dbfoxDesktop = bridge;

    expect(isEngineDesktopHost()).toBe(true);
    vi.mocked(bridge.files.pickProjectFolder).mockResolvedValue("C:\\project");
    vi.mocked(bridge.lifecycle.getRecoveryStatus).mockResolvedValue({ previousUncleanExit: false });
    expect((await getDesktopEngineConfig()).generation).toBe(3);
    expect(await getDesktopEngineStatus()).toEqual(status);
    expect(await pickDesktopProjectFolder()).toBe("C:\\project");
    await openDesktopDiagnosticLogs();
    expect(await getDesktopLaunchRecoveryStatus()).toEqual({ previousUncleanExit: false });
    await restartDesktopEngine();
    const listener = vi.fn();
    expect(await subscribeDesktopEngineState(listener)).toBe(unsubscribe);
    expect(listener).toHaveBeenCalledWith(status);
    expect(bridge.shell.openDiagnosticLogs).toHaveBeenCalledOnce();
    expect(mockInvoke).not.toHaveBeenCalled();
    expect(mockListen).not.toHaveBeenCalled();
  });

  it("keeps the current Tauri engine contract until the atomic release cutover", async () => {
    mockIsTauri.mockReturnValue(true);
    mockInvoke.mockResolvedValueOnce({ generation: 1 });

    expect(isEngineDesktopHost()).toBe(true);
    expect(await getDesktopEngineConfig()).toEqual({ generation: 1 });
    expect(mockInvoke).toHaveBeenCalledWith("get_engine_config");
  });
});
