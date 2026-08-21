import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import type {
  DbfoxDesktopBridge,
  EngineConfig,
  EngineStartupStatus,
} from "../../shared/desktopContract";

declare global {
  interface Window {
    dbfoxDesktop?: DbfoxDesktopBridge;
  }
}

function electronBridge(): DbfoxDesktopBridge | null {
  return window.dbfoxDesktop?.runtime === "electron" ? window.dbfoxDesktop : null;
}

export function isEngineDesktopHost(): boolean {
  return electronBridge() !== null || isTauri();
}

export async function getDesktopEngineConfig(): Promise<EngineConfig> {
  const electron = electronBridge();
  if (electron !== null) return electron.engine.getConfig();
  return invoke<EngineConfig>("get_engine_config");
}

export async function getDesktopEngineStatus(): Promise<EngineStartupStatus> {
  const electron = electronBridge();
  if (electron !== null) return electron.engine.getStatus();
  return invoke<EngineStartupStatus>("get_engine_startup_status");
}

export async function restartDesktopEngine(): Promise<void> {
  const electron = electronBridge();
  if (electron !== null) return electron.engine.restart();
  await invoke("restart_python_engine");
}

export async function subscribeDesktopEngineState(
  listener: (status: EngineStartupStatus) => void,
): Promise<() => void> {
  const electron = electronBridge();
  if (electron !== null) return electron.engine.subscribe(listener);
  return listen<EngineStartupStatus>("dbfox://engine-state", (event) => listener(event.payload));
}

export async function openDesktopDiagnosticLogs(): Promise<void> {
  if (electronBridge() !== null) {
    throw new Error("Electron diagnostic log integration has not migrated yet");
  }
  await invoke("open_diagnostic_logs");
}
