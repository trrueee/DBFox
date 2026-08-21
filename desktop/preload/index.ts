import { contextBridge, ipcRenderer } from "electron";

import {
  DESKTOP_CHANNELS,
  type DbfoxDesktopBridge,
  type EngineConfig,
  type EngineStartupStatus,
  type DiagnosticBundlePayload,
} from "../shared/desktopContract";

const bridge: DbfoxDesktopBridge = Object.freeze({
  runtime: "electron",
  engine: Object.freeze({
    getConfig: () => ipcRenderer.invoke(DESKTOP_CHANNELS.getEngineConfig) as Promise<EngineConfig>,
    getStatus: () => ipcRenderer.invoke(DESKTOP_CHANNELS.getEngineStatus) as Promise<EngineStartupStatus>,
    restart: () => ipcRenderer.invoke(DESKTOP_CHANNELS.restartEngine) as Promise<void>,
    subscribe(listener: (status: EngineStartupStatus) => void): () => void {
      const handler = (_event: Electron.IpcRendererEvent, status: EngineStartupStatus) => listener(status);
      ipcRenderer.on(DESKTOP_CHANNELS.engineState, handler);
      return () => ipcRenderer.removeListener(DESKTOP_CHANNELS.engineState, handler);
    },
  }),
  window: Object.freeze({
    isMaximized: () => ipcRenderer.invoke(DESKTOP_CHANNELS.windowIsMaximized) as Promise<boolean>,
    minimize: () => ipcRenderer.invoke(DESKTOP_CHANNELS.windowMinimize) as Promise<void>,
    toggleMaximize: () => ipcRenderer.invoke(DESKTOP_CHANNELS.windowToggleMaximize) as Promise<boolean>,
    close: () => ipcRenderer.invoke(DESKTOP_CHANNELS.windowClose) as Promise<void>,
    subscribe(listener: (maximized: boolean) => void): () => void {
      const handler = (_event: Electron.IpcRendererEvent, maximized: boolean) => listener(maximized);
      ipcRenderer.on(DESKTOP_CHANNELS.windowState, handler);
      return () => ipcRenderer.removeListener(DESKTOP_CHANNELS.windowState, handler);
    },
  }),
  files: Object.freeze({
    pickProjectFolder: () => ipcRenderer.invoke(DESKTOP_CHANNELS.pickProjectFolder) as Promise<string | null>,
    listProjectFolder: (path: string) => ipcRenderer.invoke(DESKTOP_CHANNELS.listProjectFolder, path),
    readProjectFile: (path: string) => ipcRenderer.invoke(DESKTOP_CHANNELS.readProjectFile, path),
    pickDlcPackage: () => ipcRenderer.invoke(DESKTOP_CHANNELS.pickDlcPackage) as Promise<string | null>,
    saveExternalImage: (url: string) => ipcRenderer.invoke(DESKTOP_CHANNELS.saveExternalImage, url),
  }),
  shell: Object.freeze({
    openExternalHttps: (url: string) => ipcRenderer.invoke(DESKTOP_CHANNELS.openExternalHttps, url) as Promise<void>,
    openDiagnosticLogs: () => ipcRenderer.invoke(DESKTOP_CHANNELS.openDiagnosticLogs) as Promise<void>,
  }),
  diagnostics: Object.freeze({
    exportBundle: (payload: DiagnosticBundlePayload) => ipcRenderer.invoke(DESKTOP_CHANNELS.exportDiagnosticBundle, payload),
  }),
  lifecycle: Object.freeze({
    getRecoveryStatus: () => ipcRenderer.invoke(DESKTOP_CHANNELS.getLaunchRecoveryStatus),
  }),
});

contextBridge.exposeInMainWorld("dbfoxDesktop", bridge);
