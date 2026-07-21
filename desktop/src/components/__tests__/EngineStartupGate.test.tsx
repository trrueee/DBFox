import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { invokeMock, waitForConfigMock, waitForHealthMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  waitForConfigMock: vi.fn(),
  waitForHealthMock: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: invokeMock }));

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
}));

import { EngineStartupGate } from "../EngineStartupGate";
import { ApiError } from "../../lib/api/client";

afterEach(() => {
  cleanup();
  invokeMock.mockReset();
  waitForConfigMock.mockReset();
  waitForHealthMock.mockReset();
  Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
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

    expect(screen.getByText("正在加载，请稍候…")).toBeTruthy();
    expect(screen.queryByText("Workspace ready")).toBeNull();

    await act(async () => {
      releaseConfig();
    });

    await waitFor(() => expect(waitForHealthMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("Workspace ready")).toBeTruthy();
  });

  it("shows the branded loading mark and a concise failure reason", async () => {
    waitForConfigMock.mockRejectedValue(
      new ApiError("startup failed", 503, "ENGINE_STARTUP_FAILED"),
    );

    const { container } = render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    expect(container.querySelector(".engine-startup-gate__mark img")?.getAttribute("src")).toBe(
      "/assets/fox/png/fox-icon-app-transparent-512.png",
    );
    expect(await screen.findByText("DBFox 启动失败，请重试或查看诊断日志。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重试启动" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "打开诊断日志" })).toBeTruthy();
  });

  it("restarts the desktop engine and mounts children after retry succeeds", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    waitForConfigMock
      .mockRejectedValueOnce(new ApiError("stopped", 503, "ENGINE_STOPPED"))
      .mockResolvedValueOnce(undefined);
    waitForHealthMock.mockResolvedValue(undefined);
    invokeMock.mockResolvedValue(undefined);

    render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "重试启动" }));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith("restart_python_engine"));
    expect(await screen.findByText("Workspace ready")).toBeTruthy();
  });

  it("opens the desktop diagnostic log directory from the failure state", async () => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { configurable: true, value: {} });
    waitForConfigMock.mockRejectedValue(
      new ApiError("health unavailable", 503, "ENGINE_HEALTH_UNAVAILABLE"),
    );
    invokeMock.mockResolvedValue(undefined);

    render(
      <EngineStartupGate>
        <div>Workspace ready</div>
      </EngineStartupGate>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "打开诊断日志" }));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith("open_diagnostic_logs"));
    expect(await screen.findByText("已打开诊断日志目录。")).toBeTruthy();
  });
});
