import { AlertTriangle, Download, RefreshCw, RotateCcw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { SettingsContent, SettingsSection, SettingsStatus } from "../../components/settings";
import { Button } from "../../components/ui/button";
import { getUserErrorMessage } from "../../lib/api/client";
import {
  checkForDesktopUpdate,
  getDesktopLaunchRecoveryStatus,
  getDesktopUpdateConfiguration,
  installPendingDesktopUpdate,
  isEngineDesktopHost,
  type LaunchRecoveryStatus,
  type UpdateCheckResult,
  type UpdateConfiguration,
} from "../../lib/desktopHost";
import "./UpdateSettingsPanel.css";

interface UpdateSettingsPanelProps {
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}

export function UpdateSettingsPanel({ showToast }: UpdateSettingsPanelProps) {
  const desktopRuntime = isEngineDesktopHost();
  const [configuration, setConfiguration] = useState<UpdateConfiguration | null>(() => (
    desktopRuntime ? null : {
      configured: false, channel: "stable", currentVersion: "开发预览", platformPolicy: "development",
    }
  ));
  const [recovery, setRecovery] = useState<LaunchRecoveryStatus | null>(() => (
    desktopRuntime ? null : { previousUncleanExit: false }
  ));
  const [update, setUpdate] = useState<UpdateCheckResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!desktopRuntime) return () => { cancelled = true; };

    void Promise.all([
      getDesktopUpdateConfiguration(),
      getDesktopLaunchRecoveryStatus(),
    ]).then(([nextConfiguration, nextRecovery]) => {
      if (!cancelled) {
        setConfiguration(nextConfiguration);
        setRecovery(nextRecovery);
      }
    }).catch((error) => {
      if (!cancelled) showToast(getUserErrorMessage(error, "无法读取桌面发布状态"), "error");
    });
    return () => { cancelled = true; };
  }, [desktopRuntime, showToast]);

  const checkForUpdate = useCallback(async () => {
    if (!configuration?.configured || checking) return;
    setChecking(true);
    try {
      const result = await checkForDesktopUpdate();
      setUpdate(result);
      showToast(
        result.available ? `发现 DBFox ${result.version}` : "当前已是最新版本",
        result.available ? "info" : "success",
      );
    } catch (error) {
      showToast(getUserErrorMessage(error, "检查更新失败"), "error");
    } finally {
      setChecking(false);
    }
  }, [checking, configuration?.configured, showToast]);

  const installUpdate = async () => {
    if (!update?.available || installing) return;
    setInstalling(true);
    try {
      showToast("正在下载并验证发布者签名，安装开始后应用会安全退出", "info");
      await installPendingDesktopUpdate();
    } catch (error) {
      setInstalling(false);
      showToast(getUserErrorMessage(error, "更新安装失败"), "error");
    }
  };

  const configured = Boolean(configuration?.configured);
  const systemManaged = configuration?.platformPolicy === "system-package-manager";
  return (
    <SettingsContent>
      <SettingsStatus
        tone={configured ? "success" : "warning"}
        label={configured ? "代码签名更新通道已启用" : systemManaged ? "由系统包管理器负责更新" : "此构建未启用自动更新"}
        description={configured
          ? "手动检查只读取官方发布清单；Windows 或 macOS 更新必须匹配已安装应用的代码签名身份。"
          : systemManaged
            ? "Linux 不从应用内安装更新，请使用发行包或系统包管理器完成升级。"
            : "开发构建不会联网检查更新，也不能安装未签名更新包。"}
        meta={`版本：${configuration?.currentVersion ?? "读取中…"} · 通道：${configuration?.channel ?? "stable"}`}
      />

      <SettingsSection
        icon={Download}
        title="应用更新"
        description="仅在你手动触发时检查；DBFox 不接受 Renderer 提供的更新 URL。"
        trailing={(
          <Button variant="outline" size="sm" disabled={!configured || checking} onClick={() => void checkForUpdate()}>
            <RefreshCw size={14} aria-hidden="true" />
            {checking ? "检查中…" : "检查更新"}
          </Button>
        )}
      >
        {update?.available ? (
          <div className="update-release">
            <div>
              <strong>DBFox {update.version}</strong>
              <span>{formatPublishDate(update.publishedAtUnix)}</span>
            </div>
            {update.body ? <p>{update.body}</p> : null}
            <Button disabled={installing} onClick={() => void installUpdate()}>
              <Download size={14} aria-hidden="true" />
              {installing ? "正在准备安装…" : "下载、验证并安装"}
            </Button>
          </div>
        ) : (
          <SettingsStatus
            tone="neutral"
            label={update ? "当前已是最新版本" : "尚未执行手动检查"}
            description="发现新版本后，由你确认才会下载和安装；安装阶段会安全停止 Sidecar 并退出应用。"
          />
        )}
      </SettingsSection>

      <SettingsSection
        icon={recovery?.previousUncleanExit ? AlertTriangle : RotateCcw}
        title="异常退出恢复"
        description="启动标记只记录上一次是否正常退出，不包含窗口内容、SQL、会话、Token 或凭据。"
      >
        <SettingsStatus
          tone={recovery?.previousUncleanExit ? "warning" : "success"}
          label={recovery?.previousUncleanExit ? "检测到上次异常退出" : "上次会话正常结束"}
          description={recovery?.previousUncleanExit
            ? "原生窗口状态会恢复；Agent 对话和工件继续以数据库为事实来源。若运行异常，请导出诊断包。"
            : "应用内面板和持久化工作区会从各自的唯一事实来源恢复。"}
        />
      </SettingsSection>

      <SettingsSection
        icon={ShieldCheck}
        title="发布安全边界"
        description="更新元数据完整性、平台代码签名与发布 provenance 是相互独立的门禁。"
      >
        <ul className="update-security-list">
          <li>Electron Builder 生成带 SHA-512 的更新元数据；应用不接受 UI 传入的 feed 或下载地址。</li>
          <li>Windows NSIS 必须通过 Authenticode，macOS App/DMG 必须通过 Developer ID 与 notarization。</li>
          <li>更新器禁止预发布、降级和 Web installer；Linux 明确交由系统包管理器，不伪造签名边界。</li>
        </ul>
      </SettingsSection>
    </SettingsContent>
  );
}

function formatPublishDate(value: number | null): string {
  if (value === null) return "发布时间未知";
  return new Date(value * 1000).toLocaleString();
}
