import { PassThrough } from "node:stream";

import { describe, expect, it } from "vitest";

import {
  EngineSupervisor,
  type EngineChild,
  type EngineExit,
  type EngineHealthProbe,
  type EngineLauncher,
} from "../engine";

class FakeEngineChild implements EngineChild {
  readonly stdout = new PassThrough();
  readonly pid: number;
  stopped = false;
  stopError: Error | null = null;
  readonly #exitListeners = new Set<(exit: EngineExit) => void>();

  constructor(pid: number) {
    this.pid = pid;
  }

  onExit(listener: (exit: EngineExit) => void): () => void {
    this.#exitListeners.add(listener);
    return () => this.#exitListeners.delete(listener);
  }

  async stop(): Promise<void> {
    if (this.stopError !== null) throw this.stopError;
    this.stopped = true;
  }

  stage(stage: string): void {
    this.stdout.write(`DBFOX_ENGINE_STAGE ${JSON.stringify({ stage })}\n`);
  }

  ready(overrides: Record<string, unknown> = {}): void {
    this.stdout.write(`DBFOX_ENGINE_READY ${JSON.stringify({
      port: 18_625 + this.pid,
      protocolVersion: 1,
      serverInfo: { name: "dbfox-engine", version: "test" },
      capabilities: ["http", "sse", "problem-details"],
      ...overrides,
    })}\n`);
  }

  exit(code = 1): void {
    const listeners = [...this.#exitListeners];
    this.#exitListeners.clear();
    for (const listener of listeners) listener({ code, signal: null });
  }
}

class FakeLauncher implements EngineLauncher {
  readonly launched: FakeEngineChild[] = [];
  readonly tokens: string[] = [];
  readonly #readyOverrides: Record<string, unknown>[];

  constructor(readyOverrides: Record<string, unknown>[] = []) {
    this.#readyOverrides = readyOverrides;
  }

  async launch(token: string): Promise<EngineChild> {
    const child = new FakeEngineChild(this.launched.length + 1);
    const overrides = this.#readyOverrides[this.launched.length] ?? {};
    this.launched.push(child);
    this.tokens.push(token);
    setTimeout(() => {
      child.stage("migrating");
      child.ready(overrides);
    }, 0);
    return child;
  }
}

class FakeHealthProbe implements EngineHealthProbe {
  readonly calls: Array<{ port: number; token: string }> = [];

  async waitUntilHealthy(port: number, token: string): Promise<void> {
    this.calls.push({ port, token });
  }
}

function supervisor(
  launcher: FakeLauncher,
  probe = new FakeHealthProbe(),
  options: ConstructorParameters<typeof EngineSupervisor>[2] = {},
): EngineSupervisor {
  let tokenSequence = 0;
  return new EngineSupervisor(launcher, probe, {
    startupTimeoutMs: 500,
    restartBackoffMs: () => 0,
    tokenFactory: () => (++tokenSequence).toString(16).padStart(64, "0"),
    ...options,
  });
}

async function waitFor(predicate: () => boolean): Promise<void> {
  const deadline = Date.now() + 1_000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("Timed out waiting for supervisor state");
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
}

describe("Electron EngineSupervisor", () => {
  it("publishes config only after an authenticated compatible generation is healthy", async () => {
    const launcher = new FakeLauncher();
    const probe = new FakeHealthProbe();
    const host = supervisor(launcher, probe);
    const stages: Array<string | null> = [];
    host.subscribe((status) => stages.push(status.stage));

    expect(() => host.config()).toThrow("unavailable");
    await host.start();

    const config = host.config();
    expect(config).toMatchObject({
      generation: 1,
      port: 18_626,
      protocolVersion: 1,
      serverInfo: { name: "dbfox-engine", version: "test" },
    });
    expect(config.token).toHaveLength(64);
    expect(probe.calls).toEqual([{ port: config.port, token: config.token }]);
    expect(stages).toContain("migrating");
    expect(host.status()).toMatchObject({ state: "ready", generation: 1 });
  });

  it("fails closed before health when the sidecar handshake is incompatible", async () => {
    const launcher = new FakeLauncher([{ protocolVersion: 2 }]);
    const probe = new FakeHealthProbe();
    const host = supervisor(launcher, probe);

    await host.start();

    expect(host.status()).toMatchObject({ state: "failed", stage: "failed" });
    expect(host.status().error).toContain("expected 1, received 2");
    expect(probe.calls).toEqual([]);
    expect(launcher.launched[0].stopped).toBe(true);
    expect(() => host.config()).toThrow("unavailable");
  });

  it("manual restart stops the old process and rotates token and generation", async () => {
    const launcher = new FakeLauncher();
    const host = supervisor(launcher);
    await host.start();
    const first = host.config();

    await host.restart();
    const second = host.config();

    expect(launcher.launched[0].stopped).toBe(true);
    expect(second.generation).toBe(2);
    expect(second.token).not.toBe(first.token);
    expect(second.port).not.toBe(first.port);
  });

  it("invalidates stale config and recovers an unexpected exit with a new token", async () => {
    const launcher = new FakeLauncher();
    const host = supervisor(launcher);
    const states: string[] = [];
    host.subscribe((status) => states.push(status.state));
    await host.start();
    const first = host.config();

    launcher.launched[0].exit(7);
    expect(() => host.config()).toThrow("unavailable");
    await waitFor(() => host.status().state === "ready" && host.status().generation === 2);

    expect(host.config().token).not.toBe(first.token);
    expect(host.status().restartCount).toBe(1);
    expect(states).toContain("restarting");
  });

  it("stops fail-closed after the bounded crash-loop budget", async () => {
    const launcher = new FakeLauncher();
    const host = supervisor(launcher, new FakeHealthProbe(), { restartLimit: 3 });
    await host.start();

    for (let restart = 1; restart <= 3; restart += 1) {
      launcher.launched[restart - 1].exit(10 + restart);
      await waitFor(
        () => host.status().state === "ready" && host.status().generation === restart + 1,
      );
    }
    launcher.launched[3].exit(20);
    await waitFor(() => host.status().state === "failed");

    expect(host.status()).toMatchObject({ stage: "crash_loop", restartCount: 4 });
    expect(host.status().error).toContain("more than 3 times");
    expect(launcher.launched).toHaveLength(4);
    expect(new Set(launcher.tokens).size).toBe(4);
    expect(() => host.config()).toThrow("unavailable");
  });

  it("cancels the active generation and exposes stopped truth on shutdown", async () => {
    const launcher = new FakeLauncher();
    const host = supervisor(launcher);
    await host.start();

    await host.stop();

    expect(launcher.launched[0].stopped).toBe(true);
    expect(host.status().state).toBe("stopped");
    expect(() => host.config()).toThrow("unavailable");
  });

  it("does not launch a replacement when the old process tree cannot stop", async () => {
    const launcher = new FakeLauncher();
    const host = supervisor(launcher);
    await host.start();
    launcher.launched[0].stopError = new Error("process tree remained alive");

    await expect(host.restart()).rejects.toThrow("process tree remained alive");

    expect(host.status()).toMatchObject({ state: "failed", stage: "shutdown_failed" });
    expect(launcher.launched).toHaveLength(1);
    expect(() => host.config()).toThrow("unavailable");
  });

  it("waits for an in-flight launch and reaps the late child during shutdown", async () => {
    const lateChild = new FakeEngineChild(99);
    let releaseLaunch: ((child: EngineChild) => void) | undefined;
    const launcher: EngineLauncher = {
      launch: () => new Promise<EngineChild>((resolveLaunch) => {
        releaseLaunch = resolveLaunch;
      }),
    };
    const host = new EngineSupervisor(launcher, new FakeHealthProbe(), {
      startupTimeoutMs: 500,
    });

    const starting = host.start();
    await waitFor(() => releaseLaunch !== undefined);
    const stopping = host.stop();
    let stopCompleted = false;
    void stopping.then(() => {
      stopCompleted = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(stopCompleted).toBe(false);

    releaseLaunch?.(lateChild);
    await Promise.all([starting, stopping]);

    expect(lateChild.stopped).toBe(true);
    expect(host.status().state).toBe("stopped");
  });
});
