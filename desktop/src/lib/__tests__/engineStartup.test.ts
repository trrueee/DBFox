import { beforeEach, expect, it, vi } from "vitest";

const { status, config } = vi.hoisted(() => ({ status: vi.fn(), config: vi.fn() }));
vi.mock("../desktopHost", () => ({
  isEngineDesktopHost: () => true,
  getDesktopEngineStatus: status,
  getDesktopEngineConfig: config,
  subscribeDesktopEngineState: vi.fn(),
}));

import { waitForEngineConfig } from "../api/client";

beforeEach(() => { status.mockReset(); config.mockReset(); });

it("ends polling on an already failed Host and preserves its structured cause", async () => {
  status.mockResolvedValue({ state: "failed", stage: "migrating", error: "metadata failed",
    failure: { code: "DBFOX_METADATA_FOREIGN_KEY_VIOLATION", fingerprint: "synthetic" } });
  await expect(waitForEngineConfig({ attempts: 2, intervalMs: 0 })).rejects.toMatchObject({
    code: "DBFOX_METADATA_FOREIGN_KEY_VIOLATION",
    detail: { stage: "migrating", fingerprint: "synthetic" },
  });
  expect(status).toHaveBeenCalledTimes(1);
});

it("rejects an incompatible ready configuration instead of polling it forever", async () => {
  status.mockResolvedValue({ state: "ready", generation: 1 });
  config.mockResolvedValue({ port: 0 });
  await expect(waitForEngineConfig({ attempts: 2, intervalMs: 0 })).rejects.toMatchObject({ code: "ENGINE_CONFIG_INVALID" });
  expect(status).toHaveBeenCalledTimes(1);
});
