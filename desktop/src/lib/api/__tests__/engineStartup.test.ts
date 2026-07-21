import { afterEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock,
}));

import { waitForEngineConfig } from "../client";

function enableTauriRuntime(): void {
  Object.defineProperty(window, "__TAURI_INTERNALS__", {
    configurable: true,
    value: {},
  });
}

afterEach(() => {
  invokeMock.mockReset();
  delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
});

describe("local engine startup coordination", () => {
  it("waits for the host lifecycle to become ready before requesting a port", async () => {
    enableTauriRuntime();
    const states: string[] = [];
    invokeMock
      .mockResolvedValueOnce({ state: "starting", error: null })
      .mockResolvedValueOnce({ state: "ready", error: null })
      .mockResolvedValueOnce({ port: 18731, token: "test-engine-token" });

    await waitForEngineConfig({
      attempts: 3,
      intervalMs: 0,
      onStatus(status) {
        states.push(status.state);
      },
    });

    expect(states).toEqual(["starting", "ready"]);
    expect(invokeMock.mock.calls.map(([command]) => command)).toEqual([
      "get_engine_startup_status",
      "get_engine_startup_status",
      "get_engine_config",
    ]);
  });

  it("fails fast when the host reports a terminal startup failure", async () => {
    enableTauriRuntime();
    invokeMock.mockResolvedValueOnce({ state: "failed", error: "sidecar exited" });

    await expect(waitForEngineConfig({ attempts: 3, intervalMs: 0 })).rejects.toMatchObject({
      code: "ENGINE_STARTUP_FAILED",
      status: 503,
    });
    expect(invokeMock).toHaveBeenCalledTimes(1);
  });
});
