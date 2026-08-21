import { app, BrowserWindow, ipcMain, type IpcMainInvokeEvent } from "electron";
import { fileURLToPath } from "node:url";

import { DESKTOP_CHANNELS } from "../shared/desktopContract";
import { EngineSupervisor } from "./engine";
import { createDevelopmentEngineLauncher, createEngineHealthProbe } from "./nodeEngineHost";
import { developmentRendererUrl } from "./security";

const rendererUrl = developmentRendererUrl(
  process.env.DBFOX_ELECTRON_RENDERER_URL ?? "http://127.0.0.1:5173",
);
const rendererOrigin = rendererUrl.origin;
const smokeMode = process.env.DBFOX_ELECTRON_SMOKE === "1";
const preloadPath = fileURLToPath(new URL("../preload/index.cjs", import.meta.url));
const supervisor = new EngineSupervisor(
  createDevelopmentEngineLauncher(rendererOrigin),
  createEngineHealthProbe(rendererOrigin),
);

let mainWindow: BrowserWindow | null = null;
let shutdownStarted = false;
let shutdownComplete = false;

function validateSender(event: IpcMainInvokeEvent): void {
  const frameUrl = event.senderFrame?.url;
  if (!frameUrl || new URL(frameUrl).origin !== rendererOrigin) {
    throw new Error("Rejected desktop IPC from an untrusted renderer");
  }
}

function registerEngineIpc(): void {
  ipcMain.handle(DESKTOP_CHANNELS.getEngineConfig, (event) => {
    validateSender(event);
    return supervisor.config();
  });
  ipcMain.handle(DESKTOP_CHANNELS.getEngineStatus, (event) => {
    validateSender(event);
    return supervisor.status();
  });
  ipcMain.handle(DESKTOP_CHANNELS.restartEngine, async (event) => {
    validateSender(event);
    await supervisor.restart();
  });
}

function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    show: false,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, targetUrl) => {
    if (new URL(targetUrl).origin !== rendererOrigin) event.preventDefault();
  });
  if (!smokeMode) window.once("ready-to-show", () => window.show());
  void window.loadURL(rendererUrl.href);
  return window;
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow === null) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });
  app.whenReady().then(async () => {
    if (app.isPackaged) {
      throw new Error("Electron packaged releases remain disabled until the R7.0c release cutover");
    }
    registerEngineIpc();
    mainWindow = createMainWindow();
    supervisor.subscribe((status) => {
      if (mainWindow !== null && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send(DESKTOP_CHANNELS.engineState, status);
      }
    });
    await supervisor.start();
    if (smokeMode) {
      await waitForRendererLoad(mainWindow);
      const rendererProof = await mainWindow.webContents.executeJavaScript(
        `(async () => ({
          runtime: window.dbfoxDesktop?.runtime,
          generation: (await window.dbfoxDesktop?.engine.getConfig())?.generation
        }))()`,
        true,
      ) as { runtime?: unknown; generation?: unknown };
      if (rendererProof.runtime !== "electron" || rendererProof.generation !== 1) {
        throw new Error("Electron preload bridge did not expose the ready Engine generation");
      }
      const config = supervisor.config();
      console.log(JSON.stringify({
        marker: "DBFOX_ELECTRON_HOST_READY",
        runtime: rendererProof.runtime,
        generation: config.generation,
        protocolVersion: config.protocolVersion,
      }));
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 500));
      app.quit();
    }
  }).catch((error: unknown) => {
    console.error("[Electron Host] Startup failed", error);
    app.quit();
  });
}

app.on("before-quit", (event) => {
  if (shutdownComplete) return;
  event.preventDefault();
  if (shutdownStarted) return;
  shutdownStarted = true;
  void supervisor.stop()
    .catch((error: unknown) => {
      console.error("[Electron Host] Engine shutdown failed", error);
    })
    .finally(() => {
      shutdownComplete = true;
      app.quit();
    });
});

app.on("window-all-closed", () => {
  app.quit();
});

function waitForRendererLoad(window: BrowserWindow): Promise<void> {
  if (!window.webContents.isLoadingMainFrame()) return Promise.resolve();
  return new Promise((resolveLoad, reject) => {
    window.webContents.once("did-finish-load", () => resolveLoad());
    window.webContents.once("did-fail-load", (_event, code, description) => {
      reject(new Error(`Electron renderer failed to load (${code}): ${description}`));
    });
  });
}
