export const DESKTOP_CHANNELS = Object.freeze({
  getEngineConfig: "dbfox:engine:get-config",
  getEngineStatus: "dbfox:engine:get-status",
  restartEngine: "dbfox:engine:restart",
  engineState: "dbfox:engine-state",
  windowIsMaximized: "dbfox:window:is-maximized",
  windowMinimize: "dbfox:window:minimize",
  windowToggleMaximize: "dbfox:window:toggle-maximize",
  windowClose: "dbfox:window:close",
  windowState: "dbfox:window-state",
  pickProjectFolder: "dbfox:files:pick-project-folder",
  listProjectFolder: "dbfox:files:list-project-folder",
  readProjectFile: "dbfox:files:read-project-file",
  pickDlcPackage: "dbfox:files:pick-dlc-package",
  saveExternalImage: "dbfox:files:save-external-image",
  openExternalHttps: "dbfox:shell:open-external-https",
  openDiagnosticLogs: "dbfox:shell:open-diagnostic-logs",
  exportDiagnosticBundle: "dbfox:diagnostics:export-bundle",
  getLaunchRecoveryStatus: "dbfox:lifecycle:get-recovery-status",
  getUpdateConfiguration: "dbfox:update:get-configuration",
  checkForUpdate: "dbfox:update:check",
  installPendingUpdate: "dbfox:update:install-pending",
});

export type EngineStartupState = "starting" | "restarting" | "ready" | "failed" | "stopped";

export interface EngineStartupStatus {
  state: EngineStartupState;
  error: string | null;
  stage: string | null;
  generation: number;
  restartCount: number;
}

export interface EngineConfig {
  port: number;
  token: string;
  generation: number;
  protocolVersion: number;
  serverInfo: {
    name: string;
    version: string;
  };
  capabilities: string[];
}

export interface ProjectFolderEntry {
  name: string;
  path: string;
  isDir: boolean;
}

export interface ProjectFolderListing {
  path: string;
  entries: ProjectFolderEntry[];
  truncated: boolean;
  error: string | null;
}

export interface ProjectFileContent {
  path: string;
  name: string;
  content: string | null;
  binary: boolean;
  size: number;
  error: string | null;
}

export interface SaveExternalImageResult {
  status: "saved" | "cancelled";
  fileName: string | null;
  byteCount: number | null;
}

export interface DiagnosticBundlePayload {
  engineSnapshot: unknown;
  webviewSnapshot: unknown;
}

export interface DiagnosticBundleResult {
  path: string;
  sizeBytes: number;
  createdAtUnix: number;
}

export interface LaunchRecoveryStatus {
  previousUncleanExit: boolean;
}

export interface UpdateConfiguration {
  configured: boolean;
  channel: "stable";
  currentVersion: string;
  platformPolicy: "code-signed" | "system-package-manager" | "development";
}

export interface UpdateCheckResult {
  available: boolean;
  currentVersion: string;
  version: string | null;
  body: string | null;
  publishedAtUnix: number | null;
}

export interface DbfoxDesktopBridge {
  readonly runtime: "electron";
  readonly engine: {
    getConfig(): Promise<EngineConfig>;
    getStatus(): Promise<EngineStartupStatus>;
    restart(): Promise<void>;
    subscribe(listener: (status: EngineStartupStatus) => void): () => void;
  };
  readonly window: {
    isMaximized(): Promise<boolean>;
    minimize(): Promise<void>;
    toggleMaximize(): Promise<boolean>;
    close(): Promise<void>;
    subscribe(listener: (maximized: boolean) => void): () => void;
  };
  readonly files: {
    pickProjectFolder(): Promise<string | null>;
    listProjectFolder(path: string): Promise<ProjectFolderListing>;
    readProjectFile(path: string): Promise<ProjectFileContent>;
    pickDlcPackage(): Promise<string | null>;
    saveExternalImage(url: string): Promise<SaveExternalImageResult>;
  };
  readonly shell: {
    openExternalHttps(url: string): Promise<void>;
    openDiagnosticLogs(): Promise<void>;
  };
  readonly diagnostics: {
    exportBundle(payload: DiagnosticBundlePayload): Promise<DiagnosticBundleResult>;
  };
  readonly lifecycle: {
    getRecoveryStatus(): Promise<LaunchRecoveryStatus>;
  };
  readonly updates: {
    getConfiguration(): Promise<UpdateConfiguration>;
    check(): Promise<UpdateCheckResult>;
    installPending(): Promise<void>;
  };
}
