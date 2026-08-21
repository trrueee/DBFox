import { autoUpdater } from "electron-updater";

import type { UpdateCheckResult, UpdateConfiguration } from "../shared/desktopContract";

interface UpdaterInfo {
  version: string;
  releaseNotes?: string | readonly { note: string | null }[] | null;
  releaseDate?: string | null;
}

export interface AppUpdaterAdapter {
  autoDownload: boolean;
  autoInstallOnAppQuit: boolean;
  allowPrerelease: boolean;
  allowDowngrade: boolean;
  disableWebInstaller: boolean;
  checkForUpdates(): Promise<{ isUpdateAvailable: boolean; updateInfo: UpdaterInfo } | null>;
  downloadUpdate(): Promise<readonly string[]>;
  quitAndInstall(isSilent?: boolean, isForceRunAfter?: boolean): void;
}

export class AppUpdateService {
  readonly #updater: AppUpdaterAdapter;
  readonly #configuration: UpdateConfiguration;
  #pending: UpdateCheckResult | null = null;
  #checking: Promise<UpdateCheckResult> | null = null;
  #installing = false;

  constructor(updater: AppUpdaterAdapter, configuration: UpdateConfiguration) {
    this.#updater = updater;
    this.#configuration = configuration;
    this.#updater.autoDownload = false;
    this.#updater.autoInstallOnAppQuit = false;
    this.#updater.allowPrerelease = false;
    this.#updater.allowDowngrade = false;
    this.#updater.disableWebInstaller = true;
  }

  configuration(): UpdateConfiguration {
    return { ...this.#configuration };
  }

  check(): Promise<UpdateCheckResult> {
    if (!this.#configuration.configured) {
      return Promise.reject(new Error("此构建未配置可验证的应用更新通道。"));
    }
    if (this.#pending !== null) return Promise.resolve({ ...this.#pending });
    if (this.#checking !== null) return this.#checking;
    const checking = this.#checkOnce();
    this.#checking = checking;
    return checking.finally(() => {
      if (this.#checking === checking) this.#checking = null;
    });
  }

  async installPending(prepareForInstall: () => Promise<void>): Promise<void> {
    if (!this.#configuration.configured || this.#pending?.available !== true) {
      throw new Error("没有已检查并可安装的更新。");
    }
    if (this.#installing) throw new Error("应用更新正在安装。");
    this.#installing = true;
    try {
      await this.#updater.downloadUpdate();
      await prepareForInstall();
      this.#updater.quitAndInstall(false, true);
    } catch (error) {
      this.#installing = false;
      console.error("[Electron Host] application update failed", error);
      throw new Error("无法完成更新操作，请检查网络后重试或查看诊断日志。", { cause: error });
    }
  }

  async #checkOnce(): Promise<UpdateCheckResult> {
    try {
      const checked = await this.#updater.checkForUpdates();
      const info = checked?.updateInfo;
      const result: UpdateCheckResult = {
        available: checked?.isUpdateAvailable === true,
        currentVersion: this.#configuration.currentVersion,
        version: checked?.isUpdateAvailable === true && info ? bounded(info.version, 128) : null,
        body: checked?.isUpdateAvailable === true && info ? releaseBody(info.releaseNotes) : null,
        publishedAtUnix: checked?.isUpdateAvailable === true && info ? publishTime(info.releaseDate) : null,
      };
      this.#pending = result.available ? result : null;
      return { ...result };
    } catch (error) {
      console.error("[Electron Host] application update check failed", error);
      throw new Error("无法检查应用更新，请检查网络后重试或查看诊断日志。", { cause: error });
    }
  }
}

export function createAppUpdateService(options: {
  packaged: boolean;
  smokeMode: boolean;
  currentVersion: string;
  platform?: NodeJS.Platform;
}): AppUpdateService {
  const platform = options.platform ?? process.platform;
  const supportsSignedUpdates = platform === "win32" || platform === "darwin";
  return new AppUpdateService(autoUpdater, {
    configured: options.packaged && !options.smokeMode && supportsSignedUpdates,
    channel: "stable",
    currentVersion: options.currentVersion,
    platformPolicy: options.packaged
      ? (supportsSignedUpdates ? "code-signed" : "system-package-manager")
      : "development",
  });
}

function releaseBody(value: UpdaterInfo["releaseNotes"]): string | null {
  if (typeof value === "string") return bounded(value, 16_384);
  if (Array.isArray(value)) return bounded(value.map((item) => item.note ?? "").filter(Boolean).join("\n\n"), 16_384);
  return null;
}

function publishTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? Math.floor(milliseconds / 1_000) : null;
}

function bounded(value: string, maximum: number): string {
  return [...value].slice(0, maximum).join("");
}
