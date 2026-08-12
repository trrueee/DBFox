import { invoke, isTauri } from "@tauri-apps/api/core";
import { AlertTriangle, Download, RefreshCw, RotateCcw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { SettingsContent, SettingsSection, SettingsStatus } from "../../components/settings";
import { Button } from "../../components/ui/button";
import { getUserErrorMessage } from "../../lib/api/client";
import "./UpdateSettingsPanel.css";

interface UpdateConfiguration {
  configured: boolean;
  channel: string;
  currentVersion: string;
}

interface UpdateCheckResult {
  available: boolean;
  currentVersion: string;
  version: string | null;
  body: string | null;
  publishedAtUnix: number | null;
}

interface LaunchRecoveryStatus {
  previousUncleanExit: boolean;
}

interface UpdateSettingsPanelProps {
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}

export function UpdateSettingsPanel({ showToast }: UpdateSettingsPanelProps) {
  const desktopRuntime = isTauri();
  const [configuration, setConfiguration] = useState<UpdateConfiguration | null>(() => (
    desktopRuntime ? null : { configured: false, channel: "stable", currentVersion: "开发预览" }
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
      invoke<UpdateConfiguration>("get_update_configuration"),
      invoke<LaunchRecoveryStatus>("get_launch_recovery_status"),
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
      const result = await invoke<UpdateCheckResult>("check_for_app_update");
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
      showToast("正在下载并验证签名，安装开始后应用会安全退出", "info");
      await invoke("install_pending_app_update");
    } catch (error) {
      setInstalling(false);
      showToast(getUserErrorMessage(error, "更新安装失败"), "error");
    }
  };

  const configured = Boolean(configuration?.configured);
  return (
    <SettingsContent>
      <SettingsStatus
        tone={configured ? "success" : "warning"}
        label={configured ? "签名更新通道已启用" : "此构建未启用自动更新"}
        description={configured
          ? "自动检查只读取官方发布清单；安装包必须通过 Tauri Updater 的公钥签名校验。"
          : "开发构建或未注入发布公钥的构建不会联网检查更新，也不能安装未签名更新包。"}
        meta={`版本：${configuration?.currentVersion ?? "读取中…"} · 通道：${configuration?.channel ?? "stable"}`}
      />

      <SettingsSection
        icon={Download}
        title="应用更新"
        description="启动后自动静默检查一次，也可手动检查；DBFox 不自行下载或执行任意 URL。"
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
            description="发现新版本后，由你确认才会下载和安装；Windows 安装阶段会安全停止 Sidecar 并退出应用。"
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
            : "窗口位置与尺寸由官方 Window State 插件恢复，应用内面板由外观设置恢复。"}
        />
      </SettingsSection>

      <SettingsSection
        icon={ShieldCheck}
        title="发布安全边界"
        description="更新签名与 Windows Authenticode 代码签名是两套独立门禁，正式发布必须同时通过。"
      >
        <ul className="update-security-list">
          <li>更新清单与更新包使用 Tauri minisign 密钥验证，私钥仅存在于 CI Secret。</li>
          <li>Windows 安装器必须使用发布者代码签名证书签名，并在 CI 中验证 Authenticode。</li>
          <li>任何密钥缺失、签名失败或 HTTPS 清单异常都会阻止发布或安装，不提供降级通道。</li>
        </ul>
      </SettingsSection>
    </SettingsContent>
  );
}

function formatPublishDate(value: number | null): string {
  if (value === null) return "发布时间未知";
  return new Date(value * 1000).toLocaleString();
}
