import { app, BrowserWindow, dialog, ipcMain, protocol, shell, type IpcMainInvokeEvent } from "electron";
import { appendFile, mkdir, open, stat, writeFile } from "node:fs/promises";
import { basename, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  DESKTOP_CHANNELS,
  type DiagnosticBundlePayload,
  type NativeFileFilter,
  type PickFileOptions,
} from "../shared/desktopContract";
import { hasPackagedRendererOrigin, PACKAGED_RENDERER_URL, registerAppProtocol } from "./appProtocol";
import { AppUpdateService, createAppUpdateService } from "./appUpdater";
import { CrashRecoveryMarker } from "./crashRecovery";
import { exportDiagnosticBundle } from "./diagnosticBundle";
import { DlcAssetAuthority, registerDlcAssetProtocol } from "./dlcAssetProtocol";
import { EngineSupervisor } from "./engine";
import { downloadExternalImage, persistImageAtomically } from "./externalImage";
import { ProjectFolderAccess, validateDlcPackage } from "./nativeFiles";
import { createDevelopmentEngineLauncher, createEngineHealthProbe, createPackagedEngineLauncher } from "./nodeEngineHost";
import { developmentRendererUrl } from "./security";

const rendererUrl = app.isPackaged
  ? PACKAGED_RENDERER_URL
  : developmentRendererUrl(process.env.DBFOX_ELECTRON_RENDERER_URL ?? "http://127.0.0.1:5173");
// WHATWG URL reports `null` for non-special schemes. Chromium nevertheless
// serializes our privileged standard scheme as this concrete origin.
const rendererOrigin = app.isPackaged ? "dbfox-app://localhost" : rendererUrl.origin;
const smokeMode = process.env.DBFOX_ELECTRON_SMOKE === "1";
const smokeRuntimeRoot = smokeMode && process.env.DBFOX_RUNTIME_DIR
  ? resolve(process.env.DBFOX_RUNTIME_DIR)
  : null;
if (smokeRuntimeRoot !== null) {
  app.setPath("userData", join(smokeRuntimeRoot, "electron-user-data"));
  app.setPath("logs", join(smokeRuntimeRoot, "electron-logs"));
}
const preloadPath = fileURLToPath(new URL("../preload/index.cjs", import.meta.url));
const supervisor = new EngineSupervisor(
  app.isPackaged
    ? createPackagedEngineLauncher(rendererOrigin, process.resourcesPath, recordEngineStderr)
    : createDevelopmentEngineLauncher(rendererOrigin, recordEngineStderr),
  createEngineHealthProbe(rendererOrigin),
);
const dlcAssetAuthority = new DlcAssetAuthority();

protocol.registerSchemesAsPrivileged([
  { scheme: "dbfox-app", privileges: { standard: true, secure: true, supportFetchAPI: true } },
  { scheme: "dlc-asset", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

let mainWindow: BrowserWindow | null = null;
let projectFolders: ProjectFolderAccess | null = null;
let crashRecovery: CrashRecoveryMarker | null = null;
let logDirectory: string | null = null;
let engineStderrLogPath: string | null = null;
let engineStderrBytes = 0;
let engineStderrWrite: Promise<void> = Promise.resolve();
let appUpdates: AppUpdateService | null = null;
let shutdownStarted = false;
let shutdownComplete = false;
let updateInstallPrepared = false;
const pickedFiles = new Map<string, { sizeBytes: number; modifiedAtUnix: number; maxBytes: number }>();
const MAX_PICKED_FILE_BYTES = 128 * 1024 * 1024;
const MAX_ENGINE_STDERR_BYTES = 2 * 1024 * 1024;

function recordEngineStderr(chunk: Buffer): void {
  const path = engineStderrLogPath;
  const remaining = MAX_ENGINE_STDERR_BYTES - engineStderrBytes;
  if (path === null || remaining <= 0 || chunk.byteLength === 0) return;
  const bounded = chunk.subarray(0, remaining);
  engineStderrBytes += bounded.byteLength;
  engineStderrWrite = engineStderrWrite
    .then(() => appendFile(path, bounded, { mode: 0o600 }))
    .catch((error: unknown) => {
      console.error("[Electron Host] Failed to persist private engine stderr", error);
    });
}

function validateSender(event: IpcMainInvokeEvent): void {
  const frameUrl = event.senderFrame?.url;
  if (!frameUrl || !isTrustedRendererUrl(frameUrl)
    || mainWindow === null || event.sender !== mainWindow.webContents) {
    throw new Error("Rejected desktop IPC from an untrusted renderer");
  }
}

function isTrustedRendererUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl);
    if (!app.isPackaged) return url.origin === rendererOrigin;
    return hasPackagedRendererOrigin(rawUrl);
  } catch {
    return false;
  }
}

function requireWindow(): BrowserWindow {
  if (mainWindow === null || mainWindow.isDestroyed()) throw new Error("DBFox desktop window is unavailable");
  return mainWindow;
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

function registerNativeIpc(): void {
  const handle = <TArgs extends unknown[], TResult>(
    channel: string,
    operation: (event: IpcMainInvokeEvent, ...args: TArgs) => TResult | Promise<TResult>,
  ) => ipcMain.handle(channel, (event, ...args: unknown[]) => {
    validateSender(event);
    return operation(event, ...(args as TArgs));
  });
  handle(DESKTOP_CHANNELS.windowIsMaximized, () => requireWindow().isMaximized());
  handle(DESKTOP_CHANNELS.windowMinimize, () => requireWindow().minimize());
  handle(DESKTOP_CHANNELS.windowToggleMaximize, () => {
    const window = requireWindow();
    if (window.isMaximized()) window.unmaximize(); else window.maximize();
    return window.isMaximized();
  });
  handle(DESKTOP_CHANNELS.windowClose, () => requireWindow().close());
  handle(DESKTOP_CHANNELS.pickProjectFolder, async () => {
    const access = projectFolders;
    if (access === null) throw new Error("项目文件夹授权服务不可用");
    const selection = await dialog.showOpenDialog(requireWindow(), {
      title: "选择项目文件夹", properties: ["openDirectory"],
    });
    if (selection.canceled || !selection.filePaths[0]) return null;
    return access.approve(selection.filePaths[0]);
  });
  handle(DESKTOP_CHANNELS.pickFile, async (_event, rawOptions?: PickFileOptions) => {
    const options = validatePickFileOptions(rawOptions);
    const selection = await dialog.showOpenDialog(requireWindow(), {
      title: options.title,
      properties: ["openFile"],
      filters: options.filters,
    });
    if (selection.canceled || !selection.filePaths[0]) return null;
    const path = resolve(selection.filePaths[0]);
    const info = await stat(path);
    if (!info.isFile() || info.size > options.maxBytes) {
      throw new Error("所选文件超过允许大小或不是普通文件");
    }
    const suffix = extname(path).slice(1).toLowerCase();
    if (options.allowedExtensions.size > 0 && !options.allowedExtensions.has(suffix)) {
      throw new Error("所选文件类型不在允许范围内");
    }
    const modifiedAtUnix = Math.floor(info.mtimeMs);
    pickedFiles.set(path, { sizeBytes: info.size, modifiedAtUnix, maxBytes: options.maxBytes });
    return { path, name: basename(path), sizeBytes: info.size, modifiedAtUnix };
  });
  handle(DESKTOP_CHANNELS.readPickedFile, async (_event, rawPath: string) => {
    if (typeof rawPath !== "string" || rawPath !== resolve(rawPath)) {
      throw new Error("文件授权无效");
    }
    const approval = pickedFiles.get(rawPath);
    if (!approval) throw new Error("该文件尚未由用户选择授权");
    const file = await open(rawPath, "r");
    try {
      const before = await file.stat();
      if (
        !before.isFile()
        || before.size !== approval.sizeBytes
        || Math.floor(before.mtimeMs) !== approval.modifiedAtUnix
        || before.size > approval.maxBytes
      ) {
        throw new Error("所选文件已发生变化，请重新选择");
      }
      const bytes = await file.readFile();
      const after = await file.stat();
      if (
        bytes.byteLength !== approval.sizeBytes
        || after.size !== before.size
        || Math.floor(after.mtimeMs) !== Math.floor(before.mtimeMs)
      ) {
        throw new Error("读取期间文件发生变化，请重新选择");
      }
      return new Uint8Array(bytes);
    } finally {
      pickedFiles.delete(rawPath);
      await file.close();
    }
  });
  handle(DESKTOP_CHANNELS.listProjectFolder, (_event, path: string) => {
    if (projectFolders === null) throw new Error("项目文件夹授权服务不可用");
    return projectFolders.list(path);
  });
  handle(DESKTOP_CHANNELS.readProjectFile, (_event, path: string) => {
    if (projectFolders === null) throw new Error("项目文件夹授权服务不可用");
    return projectFolders.read(path);
  });
  handle(DESKTOP_CHANNELS.pickDlcPackage, async () => {
    const selection = await dialog.showOpenDialog(requireWindow(), {
      title: "选择 DBFox DLC 安装包",
      properties: ["openFile"],
      filters: [{ name: "DBFox DLC Package", extensions: ["dbfox-dlc"] }],
    });
    if (selection.canceled || !selection.filePaths[0]) return null;
    return validateDlcPackage(selection.filePaths[0]);
  });
  handle(DESKTOP_CHANNELS.openExternalHttps, async (_event, rawUrl: string) => {
    const url = validateExternalHttps(rawUrl);
    await shell.openExternal(url.href, { activate: true });
  });
  handle(DESKTOP_CHANNELS.openDiagnosticLogs, async () => {
    if (logDirectory === null) throw new Error("诊断日志目录不可用");
    const error = await shell.openPath(logDirectory);
    if (error) throw new Error(error);
  });
  handle(DESKTOP_CHANNELS.saveExternalImage, async (_event, rawUrl: string) => {
    const image = await downloadExternalImage(rawUrl);
    const selection = await dialog.showSaveDialog(requireWindow(), {
      title: "保存图片副本",
      defaultPath: image.suggestedName,
      filters: [{ name: "图片", extensions: [image.extension] }],
    });
    if (selection.canceled || !selection.filePath) return { status: "cancelled", fileName: null, byteCount: null } as const;
    const path = await persistImageAtomically(selection.filePath, image);
    return { status: "saved", fileName: path.split(/[\\/]/).pop() ?? null, byteCount: image.bytes.byteLength } as const;
  });
  handle(DESKTOP_CHANNELS.exportDiagnosticBundle, async (_event, payload: DiagnosticBundlePayload) => {
    if (logDirectory === null) throw new Error("诊断日志目录不可用");
    return exportDiagnosticBundle(logDirectory, payload, app.getVersion(), supervisor.status());
  });
  handle(DESKTOP_CHANNELS.getLaunchRecoveryStatus, () => {
    if (crashRecovery === null) throw new Error("异常退出状态不可用");
    return crashRecovery.status();
  });
  handle(DESKTOP_CHANNELS.getUpdateConfiguration, () => {
    if (appUpdates === null) throw new Error("应用更新服务不可用");
    return appUpdates.configuration();
  });
  handle(DESKTOP_CHANNELS.checkForUpdate, () => {
    if (appUpdates === null) throw new Error("应用更新服务不可用");
    return appUpdates.check();
  });
  handle(DESKTOP_CHANNELS.installPendingUpdate, async () => {
    if (appUpdates === null) throw new Error("应用更新服务不可用");
    try {
      await appUpdates.installPending(async () => {
        await supervisor.stop();
        await crashRecovery?.clear();
        updateInstallPrepared = true;
      });
    } catch (error) {
      if (updateInstallPrepared) {
        updateInstallPrepared = false;
        await supervisor.start();
      }
      throw error;
    }
  });
}

function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    show: false,
    frame: false,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  const publishWindowState = () => window.webContents.send(DESKTOP_CHANNELS.windowState, window.isMaximized());
  window.on("maximize", publishWindowState);
  window.on("unmaximize", publishWindowState);
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, targetUrl) => {
    if (!isTrustedRendererUrl(targetUrl)) event.preventDefault();
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
    app.setAppUserModelId("com.dbfox.app");
    logDirectory = app.getPath("logs");
    await mkdir(logDirectory, { recursive: true, mode: 0o700 });
    engineStderrLogPath = join(logDirectory, `engine-stderr-${process.pid}.log`);
    projectFolders = new ProjectFolderAccess(join(app.getPath("userData"), "project_folder_access.json"));
    crashRecovery = await CrashRecoveryMarker.initialize(join(app.getPath("userData"), "session-active-v1"));
    appUpdates = createAppUpdateService({
      packaged: app.isPackaged,
      smokeMode,
      currentVersion: app.getVersion(),
    });
    if (app.isPackaged) registerAppProtocol(protocol, join(app.getAppPath(), "dist"));
    registerDlcAssetProtocol(protocol, dlcAssetAuthority);
    registerEngineIpc();
    registerNativeIpc();
    mainWindow = createMainWindow();
    supervisor.subscribe((status) => {
      dlcAssetAuthority.clear();
      if (mainWindow !== null && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send(DESKTOP_CHANNELS.engineState, status);
      }
      if (status.state === "ready") {
        const config = supervisor.config();
        void dlcAssetAuthority.synchronize(config, rendererOrigin).catch((error: unknown) => {
          console.error("[Electron Host] DLC activation projection unavailable", error);
        });
      }
    });
    await supervisor.start();
    if (smokeMode) {
      await waitForRendererLoad(mainWindow);
      const rendererProof = await mainWindow.webContents.executeJavaScript(
        `(async () => ({
          runtime: window.dbfoxDesktop?.runtime,
          generation: (await window.dbfoxDesktop?.engine.getConfig())?.generation,
          inactiveDlcAssetStatus: await fetch(
            "dlc-asset://localhost/${"0".repeat(64)}/index.js"
          ).then((response) => response.status)
        }))()`,
        true,
      ) as { runtime?: unknown; generation?: unknown; inactiveDlcAssetStatus?: unknown };
      if (rendererProof.runtime !== "electron" || rendererProof.generation !== 1
        || rendererProof.inactiveDlcAssetStatus !== 403) {
        throw new Error("Electron preload/asset boundary did not expose the expected fail-closed contract");
      }
      const config = supervisor.config();
      const smokeProof = {
        marker: "DBFOX_ELECTRON_HOST_READY",
        runtime: rendererProof.runtime,
        generation: config.generation,
        protocolVersion: config.protocolVersion,
        inactiveDlcAssetStatus: rendererProof.inactiveDlcAssetStatus,
        packaged: app.isPackaged,
      };
      console.log(JSON.stringify(smokeProof));
      if (smokeRuntimeRoot !== null) {
        await writeFile(
          join(smokeRuntimeRoot, "electron-smoke-result.json"),
          `${JSON.stringify(smokeProof, null, 2)}\n`,
          { encoding: "utf8", mode: 0o600 },
        );
      }
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 500));
      app.quit();
    }
  }).catch((error: unknown) => {
    console.error("[Electron Host] Startup failed", error);
    app.quit();
  });
}

app.on("before-quit", (event) => {
  if (updateInstallPrepared) {
    shutdownComplete = true;
    return;
  }
  if (shutdownComplete) return;
  event.preventDefault();
  if (shutdownStarted) return;
  shutdownStarted = true;
  let stoppedCleanly = false;
  void supervisor.stop()
    .then(() => {
      stoppedCleanly = true;
      return crashRecovery?.clear();
    })
    .catch((error: unknown) => {
      console.error("[Electron Host] Engine shutdown failed", error);
    })
    .finally(() => {
      if (!stoppedCleanly) console.error("[Electron Host] Session marker retained after unclean shutdown");
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

function validateExternalHttps(rawUrl: string): URL {
  if (!rawUrl || rawUrl.trim() !== rawUrl) throw new Error("External URL is invalid");
  const url = new URL(rawUrl);
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password) {
    throw new Error("Only credential-free HTTPS URLs may be opened");
  }
  return url;
}

function validatePickFileOptions(raw?: PickFileOptions): {
  title: string;
  filters: NativeFileFilter[];
  allowedExtensions: Set<string>;
  maxBytes: number;
} {
  if (raw !== undefined && (raw === null || typeof raw !== "object" || Array.isArray(raw))) {
    throw new Error("文件选择参数无效");
  }
  const title = raw?.title ?? "选择文件";
  if (typeof title !== "string" || title.length < 1 || title.length > 80) {
    throw new Error("文件选择标题无效");
  }
  const maxBytes = raw?.maxBytes ?? MAX_PICKED_FILE_BYTES;
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > MAX_PICKED_FILE_BYTES) {
    throw new Error("文件大小上限无效");
  }
  const filters = raw?.filters ?? [];
  if (!Array.isArray(filters) || filters.length > 8) throw new Error("文件筛选条件无效");
  const normalized = filters.map((filter) => {
    if (!filter || typeof filter.name !== "string" || filter.name.length < 1 || filter.name.length > 40
      || !Array.isArray(filter.extensions) || filter.extensions.length < 1 || filter.extensions.length > 16) {
      throw new Error("文件筛选条件无效");
    }
    const extensions = filter.extensions.map((extension) => {
      const value = String(extension).toLowerCase();
      if (!/^[a-z0-9]{1,10}$/.test(value)) throw new Error("文件扩展名无效");
      return value;
    });
    return { name: filter.name, extensions };
  });
  return {
    title,
    filters: normalized,
    allowedExtensions: new Set(normalized.flatMap((filter) => filter.extensions)),
    maxBytes,
  };
}
