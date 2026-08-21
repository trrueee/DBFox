import { contextBridge, ipcRenderer } from "electron";

import {
  DESKTOP_CHANNELS,
  type DbfoxDesktopBridge,
  type EngineConfig,
  type EngineStartupStatus,
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
});

contextBridge.exposeInMainWorld("dbfoxDesktop", bridge);
