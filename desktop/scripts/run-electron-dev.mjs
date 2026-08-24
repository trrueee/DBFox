import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { join, resolve } from "node:path";

import electronPath from "electron";

const rendererUrl = "http://127.0.0.1:5173";
const repositoryRoot = resolve(process.cwd(), "..");
const pythonCommand = process.env.DBFOX_ELECTRON_ENGINE_COMMAND ?? "python";
const preparedSystemDlcs = prepareDevelopmentSystemDlcs(pythonCommand, repositoryRoot);
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
      DBFOX_SYSTEM_DLC_DIR: preparedSystemDlcs.package_dir,
      DBFOX_SYSTEM_DLC_MANIFEST: preparedSystemDlcs.manifest,
      ...(smokeRuntimeRoot === null ? {} : { DBFOX_RUNTIME_DIR: smokeRuntimeRoot }),
    },
    stdio: "inherit",
    windowsHide: false,
  });
  const code = await exitCode(electron);
  if (!stopping && code !== 0) process.exitCode = code ?? 1;
} finally {
  await stopAll();
  if (smokeRuntimeRoot !== null) {
    await rm(smokeRuntimeRoot, { recursive: true, force: true });
  }
}

function prepareDevelopmentSystemDlcs(python, repository) {
  const result = spawnSync(python, ["-m", "scripts.prepare_dev_system_dlcs"], {
    cwd: repository,
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.status !== 0) {
    throw new Error(`Failed to prepare signed development System DLCs: ${result.stderr || result.stdout}`);
  }
  const value = JSON.parse(result.stdout.trim());
  if (typeof value.package_dir !== "string" || typeof value.manifest !== "string") {
    throw new Error("Development System DLC preparation returned an invalid result");
  }
  return value;
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
