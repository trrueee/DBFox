import type {
  DiagnosticBundlePayload,
  DiagnosticBundleResult,
  DbfoxDesktopBridge,
  EngineConfig,
  EngineStartupStatus,
  LaunchRecoveryStatus,
  ProjectFileContent,
  ProjectFolderListing,
  NativeFileSelection,
  PickFileOptions,
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

function requireElectronBridge(): DbfoxDesktopBridge {
  const bridge = electronBridge();
  if (bridge === null) throw new Error("DBFox Electron preload bridge is unavailable");
  return bridge;
}

export function isEngineDesktopHost(): boolean {
  return electronBridge() !== null;
}

export async function getDesktopEngineConfig(): Promise<EngineConfig> {
  return requireElectronBridge().engine.getConfig();
}

export async function getDesktopEngineStatus(): Promise<EngineStartupStatus> {
  return requireElectronBridge().engine.getStatus();
}

export async function restartDesktopEngine(): Promise<void> {
  return requireElectronBridge().engine.restart();
}

export async function subscribeDesktopEngineState(
  listener: (status: EngineStartupStatus) => void,
): Promise<() => void> {
  return requireElectronBridge().engine.subscribe(listener);
}

export async function openDesktopDiagnosticLogs(): Promise<void> {
  return requireElectronBridge().shell.openDiagnosticLogs();
}

export async function pickDesktopProjectFolder(): Promise<string | null> {
  return requireElectronBridge().files.pickProjectFolder();
}

export async function pickDesktopFile(options?: PickFileOptions): Promise<NativeFileSelection | null> {
  return requireElectronBridge().files.pickFile(options);
}

export async function readDesktopPickedFile(path: string): Promise<Uint8Array> {
  return requireElectronBridge().files.readPickedFile(path);
}

export function listDesktopProjectFolder(path: string): Promise<ProjectFolderListing> {
  return requireElectronBridge().files.listProjectFolder(path);
}

export function readDesktopProjectFile(path: string): Promise<ProjectFileContent> {
  return requireElectronBridge().files.readProjectFile(path);
}

export async function pickDesktopDlcPackage(): Promise<string | null> {
  return requireElectronBridge().files.pickDlcPackage();
}

export function openDesktopExternalHttps(url: string): Promise<void> {
  return requireElectronBridge().shell.openExternalHttps(url);
}

export function saveDesktopExternalImage(url: string): Promise<SaveExternalImageResult> {
  return requireElectronBridge().files.saveExternalImage(url);
}

export function exportDesktopDiagnosticBundle(payload: DiagnosticBundlePayload): Promise<DiagnosticBundleResult> {
  return requireElectronBridge().diagnostics.exportBundle(payload);
}

export function getDesktopLaunchRecoveryStatus(): Promise<LaunchRecoveryStatus> {
  return requireElectronBridge().lifecycle.getRecoveryStatus();
}

export function getDesktopUpdateConfiguration(): Promise<UpdateConfiguration> {
  return requireElectronBridge().updates.getConfiguration();
}

export function checkForDesktopUpdate(): Promise<UpdateCheckResult> {
  return requireElectronBridge().updates.check();
}

export async function installPendingDesktopUpdate(): Promise<void> {
  return requireElectronBridge().updates.installPending();
}

export async function getDesktopWindowMaximized(): Promise<boolean> {
  return requireElectronBridge().window.isMaximized();
}

export async function minimizeDesktopWindow(): Promise<void> {
  return requireElectronBridge().window.minimize();
}

export async function toggleMaximizeDesktopWindow(): Promise<boolean> {
  return requireElectronBridge().window.toggleMaximize();
}

export async function closeDesktopWindow(): Promise<void> {
  return requireElectronBridge().window.close();
}

export async function subscribeDesktopWindowState(listener: (maximized: boolean) => void): Promise<() => void> {
  return requireElectronBridge().window.subscribe(listener);
}
