import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import electronPath from "electron";
import { createServer } from "vite";

const rendererUrl = "http://127.0.0.1:5173";
const repositoryRoot = resolve(process.cwd(), "..");
const pythonCommand = process.env.DBFOX_ELECTRON_ENGINE_COMMAND ?? "python";
const GRACEFUL_SHUTDOWN_TIMEOUT_MS = 8_000;

export async function runElectronDevelopment(options = {}) {
  const createViteServer = options.createViteServer ?? createServer;
  const spawnElectron = options.spawnElectron ?? ((path, args, spawnOptions) => spawn(path, args, spawnOptions));
  const prepareSystemDlcs = options.prepareSystemDlcs ?? prepareDevelopmentSystemDlcs;
  const createSmokeRoot = options.createSmokeRoot ?? (() => mkdtemp(join(process.cwd(), ".electron-host-smoke-")));
  const removeSmokeRoot = options.removeSmokeRoot ?? ((path) => rm(path, { recursive: true, force: true }));
  const preparedSystemDlcs = prepareSystemDlcs(pythonCommand, repositoryRoot);
  const smokeRuntimeRoot = process.env.DBFOX_ELECTRON_SMOKE === "1"
    ? await createSmokeRoot()
    : null;
  let vite = null;
  let electron = null;
  let shutdownRequested = false;
  let forceTimer = null;

  const requestShutdown = () => {
    if (shutdownRequested) return;
    shutdownRequested = true;
    if (electron === null || electron.exitCode !== null || electron.signalCode !== null) return;
    if (electron.connected) {
      electron.send({ type: "dbfox-electron-shutdown" });
    }
    forceTimer = setTimeout(() => forceStopProcessTree(electron), GRACEFUL_SHUTDOWN_TIMEOUT_MS);
    forceTimer.unref?.();
  };
  const signalHandlers = new Map();
  for (const signal of ["SIGINT", "SIGTERM"]) {
    const handler = () => requestShutdown();
    signalHandlers.set(signal, handler);
    process.once(signal, handler);
  }

  try {
    electron = spawnElectron(electronPath, ["."], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        DBFOX_ELECTRON_DEV_PARENT: "1",
        DBFOX_ELECTRON_RENDERER_URL: rendererUrl,
        DBFOX_SYSTEM_DLC_DIR: preparedSystemDlcs.package_dir,
        DBFOX_SYSTEM_DLC_MANIFEST: preparedSystemDlcs.manifest,
        ...(smokeRuntimeRoot === null ? {} : { DBFOX_RUNTIME_DIR: smokeRuntimeRoot }),
      },
      stdio: ["ignore", "inherit", "inherit", "ipc"],
      windowsHide: false,
    });
    const primary = await waitForInstanceOwnership(electron);
    if (primary) {
      process.env.NODE_ENV = "development";
      vite = await createViteServer({
        root: process.cwd(),
        mode: "development",
        server: {
          host: "127.0.0.1",
          port: 5173,
          strictPort: true,
        },
      });
      await vite.listen();
      vite.printUrls();
      electron.send({ type: "dbfox-electron-renderer-ready" });
    }
    const code = await closeCode(electron);
    if (!shutdownRequested && code !== 0) process.exitCode = code ?? 1;
  } catch (error) {
    process.exitCode = 1;
    requestShutdown();
    throw error;
  } finally {
    for (const [signal, handler] of signalHandlers) {
      process.removeListener(signal, handler);
    }
    if (electron !== null && electron.exitCode === null && electron.signalCode === null) {
      requestShutdown();
      await settlesWithin(closeCode(electron), GRACEFUL_SHUTDOWN_TIMEOUT_MS + 1_000);
    }
    if (forceTimer !== null) clearTimeout(forceTimer);
    if (vite !== null) await vite.close();
    if (smokeRuntimeRoot !== null) await removeSmokeRoot(smokeRuntimeRoot);
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

export function waitForInstanceOwnership(processHandle, timeoutMs = 15_000) {
  return new Promise((resolveOwnership, reject) => {
    const timer = setTimeout(() => finish(new Error("Timed out waiting for Electron instance ownership")), timeoutMs);
    const onMessage = (message) => {
      if (message?.type !== "dbfox-electron-instance" || typeof message.primary !== "boolean") return;
      finish(null, message.primary);
    };
    const onClose = (code) => finish(new Error(`Electron exited before reporting instance ownership (${code})`));
    const onError = (error) => finish(error);
    const finish = (error, primary) => {
      clearTimeout(timer);
      processHandle.off("message", onMessage);
      processHandle.off("close", onClose);
      processHandle.off("error", onError);
      if (error) reject(error); else resolveOwnership(primary);
    };
    processHandle.on("message", onMessage);
    processHandle.once("close", onClose);
    processHandle.once("error", onError);
  });
}

function closeCode(processHandle) {
  if (processHandle.exitCode !== null) return Promise.resolve(processHandle.exitCode);
  return new Promise((resolveExit, reject) => {
    processHandle.once("error", reject);
    processHandle.once("close", (code) => resolveExit(code));
  });
}

async function settlesWithin(promise, timeoutMs) {
  let timer;
  try {
    return await Promise.race([
      promise.then(() => true),
      new Promise((resolveTimeout) => {
        timer = setTimeout(() => resolveTimeout(false), timeoutMs);
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

function forceStopProcessTree(processHandle) {
  if (processHandle === null || processHandle.pid === undefined
    || processHandle.exitCode !== null || processHandle.signalCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(processHandle.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
    return;
  }
  processHandle.kill("SIGTERM");
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : null;
if (invokedPath === fileURLToPath(import.meta.url)) {
  await runElectronDevelopment();
}
