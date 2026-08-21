import { mkdtemp, rm } from "node:fs/promises";
import { resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { EngineSupervisor } from "../engine";
import { createDevelopmentEngineLauncher, createEngineHealthProbe } from "../nodeEngineHost";

const runtimeRoots: string[] = [];

afterEach(async () => {
  delete process.env.DBFOX_RUNTIME_DIR;
  delete process.env.DBFOX_ELECTRON_ENGINE_COMMAND;
  for (const runtimeRoot of runtimeRoots.splice(0)) {
    await rm(runtimeRoot, { recursive: true, force: true });
  }
});

describe("Electron development engine host", () => {
  it("reports a missing engine command as failed startup instead of crashing Main", async () => {
    process.env.DBFOX_ELECTRON_ENGINE_COMMAND = "dbfox-command-that-does-not-exist";
    const rendererOrigin = "http://127.0.0.1:5173";
    const host = new EngineSupervisor(
      createDevelopmentEngineLauncher(rendererOrigin),
      createEngineHealthProbe(rendererOrigin),
      { startupTimeoutMs: 1_000 },
    );

    await host.start();

    expect(host.status()).toMatchObject({ state: "failed", stage: "failed" });
    expect(host.status().error).toContain("ENOENT");
    expect(() => host.config()).toThrow("unavailable");
  });

  it("launches, authenticates, restarts, and stops the real Python Engine", async () => {
    const runtimeRoot = await mkdtemp(resolve(process.cwd(), ".electron-engine-smoke-"));
    runtimeRoots.push(runtimeRoot);
    process.env.DBFOX_RUNTIME_DIR = runtimeRoot;
    const rendererOrigin = "http://127.0.0.1:5173";
    const host = new EngineSupervisor(
      createDevelopmentEngineLauncher(rendererOrigin),
      createEngineHealthProbe(rendererOrigin),
    );

    try {
      await host.start();
      const first = host.config();
      const authenticated = await fetch(`http://127.0.0.1:${first.port}/api/v1/health`, {
        headers: { Origin: rendererOrigin, "X-Local-Token": first.token },
      });
      expect(authenticated.status).toBe(200);
      const rejected = await fetch(`http://127.0.0.1:${first.port}/api/v1/health`, {
        headers: { Origin: rendererOrigin, "X-Local-Token": "wrong-token" },
      });
      expect(rejected.status).toBe(401);

      await host.restart();
      const second = host.config();
      expect(second.generation).toBe(2);
      expect(second.token).not.toBe(first.token);
      const staleToken = await fetch(`http://127.0.0.1:${second.port}/api/v1/health`, {
        headers: { Origin: rendererOrigin, "X-Local-Token": first.token },
      });
      expect(staleToken.status).toBe(401);
      if (second.port !== first.port) {
        await expect(fetch(`http://127.0.0.1:${first.port}/api/v1/health`, {
          headers: { Origin: rendererOrigin, "X-Local-Token": first.token },
          signal: AbortSignal.timeout(500),
        })).rejects.toThrow();
      }
    } finally {
      await host.stop();
    }
    expect(host.status().state).toBe("stopped");
  }, 30_000);
});
