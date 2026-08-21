import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

import type {
  DiagnosticBundlePayload,
  DiagnosticBundleResult,
  DbfoxDesktopBridge,
  EngineConfig,
  EngineStartupStatus,
  LaunchRecoveryStatus,
  ProjectFileContent,
  ProjectFolderListing,
  SaveExternalImageResult,
  UpdateCheckResult,
  UpdateConfiguration,
} from "../../shared/desktopContract";

export type {
  DiagnosticBundlePayload,
  DiagnosticBundleResult,
  LaunchRecoveryStatus,
  ProjectFileContent,
  ProjectFolderEntry,
  ProjectFolderListing,
  SaveExternalImageResult,
  UpdateCheckResult,
  UpdateConfiguration,
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
  const electron = electronBridge();
  if (electron !== null) return electron.shell.openDiagnosticLogs();
  await invoke("open_diagnostic_logs");
}

export async function pickDesktopProjectFolder(): Promise<string | null> {
  const electron = electronBridge();
  if (electron !== null) return electron.files.pickProjectFolder();
  const result = await invoke<{ path?: string | null }>("pick_project_folder");
  return result.path ?? null;
}

export function listDesktopProjectFolder(path: string): Promise<ProjectFolderListing> {
  const electron = electronBridge();
  return electron !== null
    ? electron.files.listProjectFolder(path)
    : invoke<ProjectFolderListing>("list_project_folder", { path });
}

export function readDesktopProjectFile(path: string): Promise<ProjectFileContent> {
  const electron = electronBridge();
  return electron !== null
    ? electron.files.readProjectFile(path)
    : invoke<ProjectFileContent>("read_project_file", { path });
}

export async function pickDesktopDlcPackage(): Promise<string | null> {
  const electron = electronBridge();
  if (electron !== null) return electron.files.pickDlcPackage();
  const result = await invoke<{ path?: string | null }>("pick_dlc_package");
  return result.path ?? null;
}

export function openDesktopExternalHttps(url: string): Promise<void> {
  const electron = electronBridge();
  return electron !== null
    ? electron.shell.openExternalHttps(url)
    : invoke("open_external_https_url", { url });
}

export function saveDesktopExternalImage(url: string): Promise<SaveExternalImageResult> {
  const electron = electronBridge();
  return electron !== null
    ? electron.files.saveExternalImage(url)
    : invoke<SaveExternalImageResult>("save_external_image", { url });
}

export function exportDesktopDiagnosticBundle(payload: DiagnosticBundlePayload): Promise<DiagnosticBundleResult> {
  const electron = electronBridge();
  return electron !== null
    ? electron.diagnostics.exportBundle(payload)
    : invoke<DiagnosticBundleResult>("export_diagnostic_bundle", { payload });
}

export function getDesktopLaunchRecoveryStatus(): Promise<LaunchRecoveryStatus> {
  const electron = electronBridge();
  return electron !== null
    ? electron.lifecycle.getRecoveryStatus()
    : invoke<LaunchRecoveryStatus>("get_launch_recovery_status");
}

export function getDesktopUpdateConfiguration(): Promise<UpdateConfiguration> {
  const electron = electronBridge();
  return electron !== null
    ? electron.updates.getConfiguration()
    : invoke<UpdateConfiguration>("get_update_configuration");
}

export function checkForDesktopUpdate(): Promise<UpdateCheckResult> {
  const electron = electronBridge();
  return electron !== null
    ? electron.updates.check()
    : invoke<UpdateCheckResult>("check_for_app_update");
}

export async function installPendingDesktopUpdate(): Promise<void> {
  const electron = electronBridge();
  if (electron !== null) return electron.updates.installPending();
  await invoke("install_pending_app_update");
}

export async function getDesktopWindowMaximized(): Promise<boolean> {
  const electron = electronBridge();
  if (electron !== null) return electron.window.isMaximized();
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  return getCurrentWindow().isMaximized();
}

export async function minimizeDesktopWindow(): Promise<void> {
  const electron = electronBridge();
  if (electron !== null) return electron.window.minimize();
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().minimize();
}

export async function toggleMaximizeDesktopWindow(): Promise<boolean> {
  const electron = electronBridge();
  if (electron !== null) return electron.window.toggleMaximize();
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const window = getCurrentWindow();
  await window.toggleMaximize();
  return window.isMaximized();
}

export async function closeDesktopWindow(): Promise<void> {
  const electron = electronBridge();
  if (electron !== null) return electron.window.close();
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().close();
}

export async function subscribeDesktopWindowState(listener: (maximized: boolean) => void): Promise<() => void> {
  const electron = electronBridge();
  if (electron !== null) return electron.window.subscribe(listener);
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  const window = getCurrentWindow();
  return window.onResized(async () => listener(await window.isMaximized()));
}
