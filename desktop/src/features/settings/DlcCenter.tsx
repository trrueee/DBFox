import {
  Box,
  CheckCircle2,
  PackageOpen,
  PackagePlus,
  Power,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { SettingsContent, SettingsSection, SettingsStatus } from "../../components/settings";
import { Button } from "../../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { getUserErrorMessage } from "../../lib/api/client";
import type {
  DlcLifecycleItem,
  DlcLifecycleState,
  DlcListResponse,
  DlcPackageInspection,
} from "../../lib/api/generated/types.gen";
import {
  canManageDlcPackages,
  inspectDlcPackage,
  installDlcPackage,
  listDlcs,
  pickDlcPackage,
  restartDlcRuntime,
  setDlcEnabled,
  trustDlcPublisher,
  uninstallDlc,
} from "../../lib/dlcLifecycle";
import "./DlcCenter.css";

interface DlcCenterProps {
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}

interface InspectedPackage {
  archivePath: string;
  inspection: DlcPackageInspection;
}

const STATE_PRESENTATION: Record<DlcLifecycleState, { label: string; tone: string }> = {
  installed_disabled: { label: "已安装，未启用", tone: "neutral" },
  enable_pending_restart: { label: "等待重启启用", tone: "warning" },
  active: { label: "当前已激活", tone: "success" },
  disable_pending_restart: { label: "等待重启停用", tone: "warning" },
  activation_failed: { label: "激活失败", tone: "danger" },
};

function shortDigest(digest: string | null): string {
  return digest ? `${digest.slice(0, 12)}…` : "—";
}

function packageFileName(path: string): string {
  return path.split(/[\\/]/).at(-1) || path;
}

function upsertDlc(payload: DlcListResponse | null, item: DlcLifecycleItem): DlcListResponse {
  const current = payload ?? { snapshot_id: "", dlcs: [] };
  const next = current.dlcs.filter((candidate) => candidate.dlc_id !== item.dlc_id);
  next.push(item);
  next.sort((left, right) => left.dlc_id.localeCompare(right.dlc_id));
  return { ...current, dlcs: next };
}

export function DlcCenter({ showToast }: DlcCenterProps) {
  const desktopRuntime = canManageDlcPackages();
  const [payload, setPayload] = useState<DlcListResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<InspectedPackage | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<DlcLifecycleItem | null>(null);

  const refresh = useCallback(async () => {
    const next = await listDlcs();
    setPayload(next);
    setLoadError(null);
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    void listDlcs().then((next) => {
      if (!cancelled) {
        setPayload(next);
        setLoadError(null);
      }
    }).catch((error) => {
      if (!cancelled) setLoadError(getUserErrorMessage(error, "无法读取 DLC 列表"));
    });
    return () => { cancelled = true; };
  }, []);

  const restartRequired = useMemo(
    () => payload?.dlcs.some((item) => item.restart_state !== "none") ?? false,
    [payload],
  );

  const choosePackage = async () => {
    if (!desktopRuntime || actionKey) return;
    setActionKey("pick");
    try {
      const archivePath = await pickDlcPackage();
      if (!archivePath) return;
      const inspection = await inspectDlcPackage(archivePath);
      setCandidate({ archivePath, inspection });
    } catch (error) {
      showToast(getUserErrorMessage(error, "无法检查 DLC 安装包"), "error");
    } finally {
      setActionKey(null);
    }
  };

  const trustCandidate = async () => {
    if (!candidate || actionKey) return;
    setActionKey("trust");
    try {
      await trustDlcPublisher(candidate.archivePath, candidate.inspection);
      setCandidate((current) => current ? {
        ...current,
        inspection: {
          ...current.inspection,
          trust_required: false,
          trust_status: "trusted_signed",
        },
      } : null);
      showToast("发布者公钥已在本机受信任；安装包仍需单独确认安装", "success");
    } catch (error) {
      showToast(getUserErrorMessage(error, "无法信任此发布者"), "error");
    } finally {
      setActionKey(null);
    }
  };

  const installCandidate = async () => {
    if (!candidate || candidate.inspection.trust_required || actionKey) return;
    setActionKey("install");
    try {
      const installed = await installDlcPackage(candidate.archivePath);
      setPayload((current) => upsertDlc(current, installed));
      setCandidate(null);
      showToast(`${installed.display_name} 已安装，默认保持禁用`, "success");
    } catch (error) {
      showToast(getUserErrorMessage(error, "DLC 安装失败"), "error");
    } finally {
      setActionKey(null);
    }
  };

  const setEnabled = async (item: DlcLifecycleItem, enabled: boolean) => {
    if (actionKey) return;
    setActionKey(`${enabled ? "enable" : "disable"}:${item.dlc_id}`);
    try {
      const updated = await setDlcEnabled(item.dlc_id, enabled);
      setPayload((current) => upsertDlc(current, updated));
      showToast(
        enabled ? `${item.display_name} 将在重启后启用` : `${item.display_name} 将在重启后停用`,
        "info",
      );
    } catch (error) {
      showToast(getUserErrorMessage(error, enabled ? "无法启用 DLC" : "无法停用 DLC"), "error");
    } finally {
      setActionKey(null);
    }
  };

  const restartNow = async () => {
    if (!desktopRuntime || actionKey) return;
    setActionKey("restart");
    try {
      showToast("正在安全重启本地引擎并重建 DLC 运行时…", "info");
      await restartDlcRuntime();
      await refresh();
      showToast("本地引擎已重启，DLC 运行状态已刷新", "success");
    } catch (error) {
      showToast(getUserErrorMessage(error, "本地引擎重启失败，请查看诊断日志"), "error");
    } finally {
      setActionKey(null);
    }
  };

  const confirmUninstall = async () => {
    if (!uninstallTarget || actionKey) return;
    setActionKey(`uninstall:${uninstallTarget.dlc_id}`);
    try {
      const result = await uninstallDlc(uninstallTarget.dlc_id);
      setPayload((current) => current ? {
        ...current,
        dlcs: current.dlcs.filter((item) => item.dlc_id !== result.dlc_id),
      } : current);
      setUninstallTarget(null);
      showToast(
        result.data_retained ? "DLC 已卸载；扩展数据已保留" : "DLC 已卸载",
        "success",
      );
    } catch (error) {
      showToast(getUserErrorMessage(error, "DLC 卸载失败"), "error");
    } finally {
      setActionKey(null);
    }
  };

  const busy = actionKey !== null;
  return (
    <>
      <SettingsContent className="dlc-center" aria-busy={busy || payload === null}>
        <SettingsStatus
          tone={restartRequired ? "warning" : "info"}
          label={restartRequired ? "有 DLC 状态等待引擎重启" : "Desired state 与当前运行状态独立显示"}
          description={restartRequired
            ? "启用或停用只修改期望状态；重启成功前，当前运行能力不会被冒充为新状态。"
            : "安装不会执行扩展代码；只有启用并完成引擎重启后，选定 digest 才会进入 active runtime。"}
          meta={payload?.snapshot_id ? `Snapshot ${payload.snapshot_id.slice(0, 13)}…` : "正在读取…"}
        />

        {actionKey === "restart" ? (
          <SettingsStatus
            tone="loading"
            label="正在重启本地引擎"
            description="正在等待新的 engine generation、健康检查和 DLC runtime snapshot。"
          />
        ) : null}

        {loadError ? (
          <SettingsStatus
            tone="danger"
            label="无法读取 DLC 状态"
            description={loadError}
            meta={(
              <Button
                variant="outline"
                size="sm"
                onClick={() => void refresh().catch(() => undefined)}
              >
                重试
              </Button>
            )}
          />
        ) : null}

        <SettingsSection
          icon={PackageOpen}
          title="已安装扩展"
          description="每个扩展同时显示持久化期望状态与当前进程真实激活状态。"
          trailing={(
            <div className="dlc-center__primary-actions">
              {restartRequired ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!desktopRuntime || busy}
                  onClick={() => void restartNow()}
                >
                  <RefreshCw size={14} aria-hidden="true" />
                  立即重启
                </Button>
              ) : null}
              <Button
                size="sm"
                disabled={!desktopRuntime || busy}
                title={desktopRuntime ? undefined : "只能在 DBFox 桌面应用中选择安装包"}
                onClick={() => void choosePackage()}
              >
                <PackagePlus size={14} aria-hidden="true" />
                {actionKey === "pick" ? "正在检查…" : "从文件安装"}
              </Button>
            </div>
          )}
        >
          {payload === null && !loadError ? (
            <div className="dlc-center__loading" role="status">
              <RefreshCw className="is-spinning" size={18} aria-hidden="true" />
              正在读取本机 DLC registry…
            </div>
          ) : payload?.dlcs.length === 0 ? (
            <div className="dlc-center__empty">
              <Box size={28} aria-hidden="true" />
              <strong>尚未安装 DLC 扩展</strong>
              <span>选择一个签名的 .dbfox-dlc 文件；检查和安装阶段不会执行扩展代码。</span>
            </div>
          ) : (
            <div className="dlc-list">
              {payload?.dlcs.map((item) => (
                <DlcCard
                  key={item.dlc_id}
                  item={item}
                  busy={busy}
                  actionKey={actionKey}
                  onSetEnabled={setEnabled}
                  onRestart={restartNow}
                  onUninstall={setUninstallTarget}
                  desktopRuntime={desktopRuntime}
                />
              ))}
            </div>
          )}
        </SettingsSection>
      </SettingsContent>

      <PackageInspectionDialog
        candidate={candidate}
        actionKey={actionKey}
        onOpenChange={(open) => {
          if (!open && !busy) setCandidate(null);
        }}
        onTrust={trustCandidate}
        onInstall={installCandidate}
      />

      <Dialog
        open={uninstallTarget !== null}
        onOpenChange={(open) => {
          if (!open && !busy) setUninstallTarget(null);
        }}
      >
        <DialogContent className="dlc-confirm-dialog">
          <DialogHeader>
            <DialogTitle>卸载 {uninstallTarget?.display_name}</DialogTitle>
            <DialogDescription>
              将删除 registry 引用和未被引用的可执行包字节。DLC 自己的数据目录默认保留，重新安装后仍可继续使用。
            </DialogDescription>
          </DialogHeader>
          <SettingsStatus
            tone="info"
            label="数据保留策略"
            description={`APP_DATA/dlcs/data/${uninstallTarget?.dlc_id ?? "<dlc_id>"}/ 不会被删除。`}
          />
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setUninstallTarget(null)}>取消</Button>
            <Button variant="destructive" disabled={busy} onClick={() => void confirmUninstall()}>
              <Trash2 size={14} aria-hidden="true" />
              {actionKey?.startsWith("uninstall:") ? "正在卸载…" : "确认卸载"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DlcCard({
  item,
  busy,
  actionKey,
  onSetEnabled,
  onRestart,
  onUninstall,
  desktopRuntime,
}: {
  item: DlcLifecycleItem;
  busy: boolean;
  actionKey: string | null;
  onSetEnabled: (item: DlcLifecycleItem, enabled: boolean) => Promise<void>;
  onRestart: () => Promise<void>;
  onUninstall: (item: DlcLifecycleItem) => void;
  desktopRuntime: boolean;
}) {
  const state = STATE_PRESENTATION[item.state];
  const uninstallAllowed = !item.desired_enabled && !item.active;
  const transitionKey = `${item.desired_enabled ? "disable" : "enable"}:${item.dlc_id}`;
  return (
    <article className="dlc-card" aria-labelledby={`dlc-${item.dlc_id}`}>
      <header className="dlc-card__header">
        <div>
          <h3 id={`dlc-${item.dlc_id}`}>{item.display_name}</h3>
          <p>{item.description || "此扩展未提供说明。"}</p>
        </div>
        <span className={`dlc-state dlc-state--${state.tone}`}>
          {item.state === "active" ? <CheckCircle2 size={13} aria-hidden="true" /> : null}
          {item.state === "activation_failed" ? <TriangleAlert size={13} aria-hidden="true" /> : null}
          {state.label}
        </span>
      </header>

      <div className="dlc-truth-grid" aria-label="DLC 期望状态与运行状态">
        <div>
          <span>期望状态</span>
          <strong>{item.desired_enabled ? "启用" : "禁用"}</strong>
        </div>
        <div>
          <span>当前运行</span>
          <strong>{item.active ? "已激活" : "未激活"}</strong>
        </div>
        <div>
          <span>Selected digest</span>
          <code title={item.selected_digest}>{shortDigest(item.selected_digest)}</code>
        </div>
        <div>
          <span>Active digest</span>
          <code title={item.active_digest ?? undefined}>{shortDigest(item.active_digest)}</code>
        </div>
      </div>

      <dl className="dlc-card__metadata">
        <div><dt>ID / 版本</dt><dd><code>{item.dlc_id}</code> · {item.version}</dd></div>
        <div><dt>发布者</dt><dd>{item.publisher} · <code title={item.publisher_fingerprint ?? undefined}>{shortDigest(item.publisher_fingerprint)}</code></dd></div>
        <div><dt>Entrypoints</dt><dd>{[
          item.backend_entrypoint_present ? "Backend" : null,
          item.frontend_entrypoint_present ? "Frontend" : null,
        ].filter(Boolean).join(" + ") || "无可用入口"}</dd></div>
      </dl>

      <details className="dlc-permissions">
        <summary>权限声明（{item.permissions.length}）</summary>
        {item.permissions.length > 0 ? (
          <ul>{item.permissions.map((permission) => <li key={permission}><code>{permission}</code></li>)}</ul>
        ) : <p>未声明额外权限。</p>}
      </details>

      {item.activation_failure ? (
        <div className="dlc-activation-error" role="alert">
          <TriangleAlert size={16} aria-hidden="true" />
          <div><strong>{item.activation_failure.code}</strong><span>{item.activation_failure.message}</span></div>
        </div>
      ) : null}

      <footer className="dlc-card__actions">
        <Button
          variant={item.desired_enabled ? "outline" : "default"}
          size="sm"
          disabled={busy}
          onClick={() => void onSetEnabled(item, !item.desired_enabled)}
        >
          <Power size={14} aria-hidden="true" />
          {actionKey === transitionKey ? "正在更新…" : item.desired_enabled ? "停用" : "启用"}
        </Button>
        {item.restart_state !== "none" ? (
          <Button variant="outline" size="sm" disabled={!desktopRuntime || busy} onClick={() => void onRestart()}>
            <RefreshCw size={14} aria-hidden="true" />
            立即重启
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          disabled={busy || !uninstallAllowed}
          title={uninstallAllowed ? "卸载并保留 DLC 数据" : "请先停用并重启，确认当前运行状态为未激活"}
          onClick={() => onUninstall(item)}
        >
          <Trash2 size={14} aria-hidden="true" />
          卸载
        </Button>
        {!uninstallAllowed ? <span className="dlc-card__constraint">停用并重启后才可卸载</span> : null}
      </footer>
    </article>
  );
}

function PackageInspectionDialog({
  candidate,
  actionKey,
  onOpenChange,
  onTrust,
  onInstall,
}: {
  candidate: InspectedPackage | null;
  actionKey: string | null;
  onOpenChange: (open: boolean) => void;
  onTrust: () => Promise<void>;
  onInstall: () => Promise<void>;
}) {
  const inspection = candidate?.inspection;
  const busy = actionKey === "trust" || actionKey === "install";
  return (
    <Dialog open={candidate !== null} onOpenChange={onOpenChange}>
      <DialogContent
        className="dlc-inspection-dialog"
        onEscapeKeyDown={(event) => { if (busy) event.preventDefault(); }}
        onInteractOutside={(event) => { if (busy) event.preventDefault(); }}
      >
        <DialogHeader>
          <DialogTitle>检查 DLC 安装包</DialogTitle>
          <DialogDescription>
            已完成包结构、完整性与 Ed25519 签名真实性检查。此阶段未执行任何扩展代码。
          </DialogDescription>
        </DialogHeader>
        {candidate && inspection ? (
          <div className="dlc-inspection">
            <div className="dlc-inspection__title">
              <PackageOpen size={20} aria-hidden="true" />
              <div><strong>{inspection.display_name}</strong><span>{packageFileName(candidate.archivePath)}</span></div>
            </div>
            <p>{inspection.description || "此扩展未提供说明。"}</p>
            <dl>
              <div><dt>ID / 版本</dt><dd><code>{inspection.dlc_id}</code> · {inspection.version}</dd></div>
              <div><dt>发布者</dt><dd>{inspection.publisher}</dd></div>
              <div><dt>Publisher fingerprint</dt><dd><code>{inspection.publisher_fingerprint}</code></dd></div>
              <div><dt>Package digest</dt><dd><code>{inspection.package_digest}</code></dd></div>
              <div><dt>Entrypoints</dt><dd>{[
                inspection.backend_entrypoint_present ? "Backend" : null,
                inspection.frontend_entrypoint_present ? "Frontend" : null,
              ].filter(Boolean).join(" + ") || "无可用入口"}</dd></div>
            </dl>
            <div className="dlc-inspection__permissions">
              <strong>权限声明</strong>
              {inspection.permissions.length > 0 ? (
                <ul>{inspection.permissions.map((permission) => <li key={permission}><code>{permission}</code></li>)}</ul>
              ) : <span>未声明额外权限。</span>}
            </div>
            {inspection.trust_required ? (
              <SettingsStatus
                tone="warning"
                label="发布者尚未受信任"
                description="确认后只保存此 Ed25519 公钥；发布者名称不参与信任判定。信任操作会再次检查 digest、内嵌 key 与签名。"
                meta={<ShieldAlert size={16} aria-hidden="true" />}
              />
            ) : (
              <SettingsStatus
                tone="success"
                label="发布者公钥已受信任"
                description="安装仍默认为禁用；启用并重启前不会执行扩展代码。"
                meta={<ShieldCheck size={16} aria-hidden="true" />}
              />
            )}
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>取消</Button>
          {inspection?.trust_required ? (
            <Button disabled={busy} onClick={() => void onTrust()}>
              <ShieldCheck size={14} aria-hidden="true" />
              {actionKey === "trust" ? "正在重新验证…" : "信任此发布者"}
            </Button>
          ) : (
            <Button disabled={busy || !inspection} onClick={() => void onInstall()}>
              <PackagePlus size={14} aria-hidden="true" />
              {actionKey === "install" ? "正在安装…" : "安装（默认禁用）"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
