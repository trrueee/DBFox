import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const {
  hostAvailableMock,
  restartMock,
  openLogsMock,
  waitForConfigMock,
  waitForHealthMock,
  subscribeMock,
  engineRuntimeState,
} = vi.hoisted(() => ({
  hostAvailableMock: vi.fn(() => false),
  restartMock: vi.fn(),
  openLogsMock: vi.fn(),
  waitForConfigMock: vi.fn(),
  waitForHealthMock: vi.fn(),
  subscribeMock: vi.fn(async (
    listener: (status: { state: string; generation?: number }) => void,
  ) => {
    void listener;
    return () => undefined;
  }),
  engineRuntimeState: {
    generation: 1,
    listener: null as ((status: { state: string; generation?: number }) => void) | null,
  },
}));

vi.mock("../../lib/desktopHost", () => ({
  isEngineDesktopHost: hostAvailableMock,
  restartDesktopEngine: restartMock,
  openDesktopDiagnosticLogs: openLogsMock,
}));

vi.mock("../../lib/api/client", () => ({
  ApiError: class ApiError extends Error {
    status?: number;
    code?: string;

    constructor(message: string, status?: number, code?: string) {
      super(message);
      this.status = status;
      this.code = code;
    }
  },
  waitForEngineConfig: waitForConfigMock,
  waitEngineHealth: waitForHealthMock,
  getRuntimeSession: () => ({ generation: engineRuntimeState.generation }),
  subscribeEngineState: subscribeMock,
}));

import { EngineStartupGate } from "../EngineStartupGate";
import { ApiError } from "../../lib/api/client";

afterEach(() => {
  cleanup();
  hostAvailableMock.mockReset().mockReturnValue(false);
  restartMock.mockReset();
  openLogsMock.mockReset();
  waitForConfigMock.mockReset();
  waitForHealthMock.mockReset();
  subscribeMock.mockReset();
  subscribeMock.mockResolvedValue(() => undefined);
  engineRuntimeState.generation = 1;
  engineRuntimeState.listener = null;
});

describe("EngineStartupGate", () => {
  it("keeps the startup UI responsive and mounts children after the engine recovers", async () => {
    let releaseConfig!: () => void;
    const configReady = new Promise<void>((resolve) => {
      releaseConfig = resolve;
    });
    waitForConfigMock.mockImplementation(async (options: { onStatus?: (status: { state: string }) => void }) => {
      options.onStatus?.({ state: "starting" });
      await configReady;
    });
    waitForHealthMock.mockResolvedValue(undefined);

    render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    expect(screen.getByText("正在启动 DBFox…")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "正在启动 DBFox…" })).toBeTruthy();
    expect(screen.queryByText("Workspace ready")).toBeNull();

    await act(async () => {
      releaseConfig();
    });

    await waitFor(() => expect(waitForHealthMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Workspace ready")).toBeTruthy();
  });

  it("shows the branded Empty/Alert recovery composition and a concise failure reason", async () => {
    waitForConfigMock.mockRejectedValue(
      new ApiError("startup failed", 503, "ENGINE_STARTUP_FAILED"),
    );

    const { container } = render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    expect(container.querySelector('[data-slot="empty-icon"] img')?.getAttribute("src")).toBe(
      "/assets/fox/png/fox-icon-app-transparent-512.png",
    );
    expect(await screen.findByText("DBFox 启动失败，请重试或查看诊断日志。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重试启动" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "打开诊断日志" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("DBFox 未能启动");
  });

  it("restarts the desktop engine and mounts children after retry succeeds", async () => {
    hostAvailableMock.mockReturnValue(true);
    waitForConfigMock
      .mockRejectedValueOnce(new ApiError("stopped", 503, "ENGINE_STOPPED"))
      .mockResolvedValueOnce(undefined);
    waitForHealthMock.mockResolvedValue(undefined);
    restartMock.mockResolvedValue(undefined);

    render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "重试启动" }));

    await waitFor(() => expect(restartMock).toHaveBeenCalledOnce());
    expect(await screen.findByText("Workspace ready")).toBeTruthy();
  });

  it("keeps the workspace mounted while a newer engine generation becomes healthy", async () => {
    hostAvailableMock.mockReturnValue(true);
    waitForConfigMock
      .mockResolvedValueOnce(undefined)
      .mockImplementationOnce(async (options: { afterGeneration?: number }) => {
        expect(options.afterGeneration).toBe(1);
        engineRuntimeState.generation = 2;
      });
    waitForHealthMock.mockResolvedValue(undefined);
    subscribeMock.mockImplementation(async (listener: (
      status: { state: string; generation?: number },
    ) => void) => {
      engineRuntimeState.listener = listener;
      return () => {
        engineRuntimeState.listener = null;
      };
    });

    render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    expect(await screen.findByText("Workspace ready")).toBeTruthy();
    await waitFor(() => expect(engineRuntimeState.listener).not.toBeNull());

    act(() => {
      engineRuntimeState.listener?.({ state: "restarting", generation: 1 });
    });
    expect(screen.getByText("本地引擎意外退出，正在自动恢复…")).toBeTruthy();
    expect(screen.getByText("Workspace ready")).toBeTruthy();

    await act(async () => {
      engineRuntimeState.listener?.({ state: "ready", generation: 2 });
    });

    await waitFor(() => expect(waitForConfigMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(waitForHealthMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText("本地引擎意外退出，正在自动恢复…")).toBeNull());
    expect(screen.getByText("Workspace ready")).toBeTruthy();
  });

  it("opens the desktop diagnostic log directory from the failure state", async () => {
    hostAvailableMock.mockReturnValue(true);
    waitForConfigMock.mockRejectedValue(
      new ApiError("health unavailable", 503, "ENGINE_HEALTH_UNAVAILABLE"),
    );
    openLogsMock.mockResolvedValue(undefined);

    render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "打开诊断日志" }));

    await waitFor(() => expect(openLogsMock).toHaveBeenCalledOnce());
    expect(await screen.findByText("已打开诊断日志目录。")).toBeTruthy();
  });
});
