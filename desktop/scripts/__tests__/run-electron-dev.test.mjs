import { EventEmitter } from "node:events";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  runElectronDevelopment,
  waitForInstanceOwnership,
} from "../run-electron-dev.mjs";

class FakeElectronChild extends EventEmitter {
  constructor({ primary }) {
    super();
    this.primary = primary;
    this.pid = 42;
    this.exitCode = null;
    this.signalCode = null;
    this.connected = true;
    this.messages = [];
  }

  reportOwnership() {
    queueMicrotask(() => {
      this.emit("message", {
        type: "dbfox-electron-instance",
        primary: this.primary,
      });
      if (!this.primary) this.close(0);
    });
  }

  send(message) {
    this.messages.push(message);
    if (message.type === "dbfox-electron-renderer-ready"
      || message.type === "dbfox-electron-shutdown") {
      queueMicrotask(() => this.close(0));
    }
    return true;
  }

  kill() {
    this.close(null, "SIGTERM");
    return true;
  }

  close(code, signal = null) {
    if (this.exitCode !== null || this.signalCode !== null) return;
    this.exitCode = code;
    this.signalCode = signal;
    this.connected = false;
    this.emit("close", code, signal);
  }
}

const originalExitCode = process.exitCode;

afterEach(() => {
  process.exitCode = originalExitCode;
  delete process.env.DBFOX_ELECTRON_SMOKE;
  vi.restoreAllMocks();
});

function lifecycleOptions(child, createViteServer) {
  return {
    prepareSystemDlcs: () => ({
      package_dir: "C:/runtime/system-dlcs",
      manifest: "C:/runtime/system-dlcs/system-dlcs.json",
    }),
    spawnElectron: () => {
      child.reportOwnership();
      return child;
    },
    createViteServer,
  };
}

describe("Electron development lifecycle coordinator", () => {
  it("starts and owns Vite only after Electron wins the single-instance lock", async () => {
    const child = new FakeElectronChild({ primary: true });
    const vite = {
      listen: vi.fn(async () => undefined),
      printUrls: vi.fn(),
      close: vi.fn(async () => undefined),
    };
    const createViteServer = vi.fn(async () => vite);

    await runElectronDevelopment(lifecycleOptions(child, createViteServer));

    expect(createViteServer).toHaveBeenCalledOnce();
    expect(vite.listen).toHaveBeenCalledOnce();
    expect(child.messages).toContainEqual({
      type: "dbfox-electron-renderer-ready",
    });
    expect(vite.close).toHaveBeenCalledOnce();
  });

  it("does not touch Vite when Electron reports an existing primary instance", async () => {
    const child = new FakeElectronChild({ primary: false });
    const createViteServer = vi.fn();

    await runElectronDevelopment(lifecycleOptions(child, createViteServer));

    expect(createViteServer).not.toHaveBeenCalled();
    expect(child.messages).toEqual([]);
  });

  it("fails when Electron exits before declaring instance ownership", async () => {
    const child = new FakeElectronChild({ primary: true });
    const waiting = waitForInstanceOwnership(child, 100);
    child.close(7);

    await expect(waiting).rejects.toThrow(
      "Electron exited before reporting instance ownership (7)",
    );
  });
});
