import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { join, resolve } from "node:path";

import electronPath from "electron";

const rendererUrl = "http://127.0.0.1:5173";
const smokeRuntimeRoot = process.env.DBFOX_ELECTRON_SMOKE === "1"
  ? await mkdtemp(join(process.cwd(), ".electron-host-smoke-"))
  : null;
const vite = spawn(
  process.execPath,
  [resolve("node_modules/vite/bin/vite.js"), "--host", "127.0.0.1"],
  { cwd: process.cwd(), env: process.env, stdio: "inherit", windowsHide: true },
);
let electron = null;
let stopping = false;

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => {
    void stopAll();
  });
}

try {
  await waitForRenderer(rendererUrl, vite);
  electron = spawn(electronPath, ["."], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      DBFOX_ELECTRON_RENDERER_URL: rendererUrl,
      ...(smokeRuntimeRoot === null ? {} : { DBFOX_RUNTIME_DIR: smokeRuntimeRoot }),
    },
    stdio: "inherit",
    windowsHide: true,
  });
  const code = await exitCode(electron);
  if (!stopping && code !== 0) process.exitCode = code ?? 1;
} finally {
  await stopAll();
  if (smokeRuntimeRoot !== null) {
    await rm(smokeRuntimeRoot, { recursive: true, force: true });
  }
}

async function waitForRenderer(url, processHandle) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (processHandle.exitCode !== null) {
      throw new Error(`Vite exited before the Electron renderer was ready (${processHandle.exitCode})`);
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(500) });
      if (response.ok) return;
    } catch {
      // Retry until the bounded startup deadline.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error("Timed out waiting for the Electron renderer development server");
}

function exitCode(processHandle) {
  return new Promise((resolveExit, reject) => {
    processHandle.once("error", reject);
    processHandle.once("exit", (code) => resolveExit(code));
  });
}

async function stopAll() {
  if (stopping) return;
  stopping = true;
  stopProcessTree(electron);
  stopProcessTree(vite);
}

function stopProcessTree(processHandle) {
  if (processHandle === null || processHandle.pid === undefined || processHandle.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(processHandle.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  processHandle.kill("SIGTERM");
}
