import {
  CubeIcon,
  ArrowsLeftRightIcon,
  CheckCircleIcon,
  CaretDownIcon,
  PuzzlePieceIcon,
  PackageIcon,
  MagnifyingGlassIcon,
  ArrowsClockwiseIcon,
  ShieldWarningIcon,
  ShieldCheckIcon,
  TrashIcon,
  WarningIcon,
} from "@/components/icons";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { SettingsContent, SettingsSection, SettingsStatus } from "../../components/settings";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Switch } from "../../components/ui/switch";
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
  DlcInstalledVersionItem,
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
  removeDlcVersion,
  selectDlcVersion,
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

interface RemoveVersionTarget {
  item: DlcLifecycleItem;
  version: DlcInstalledVersionItem;
}

interface DlcActionError {
  scope: "page" | "inspection" | "remove" | "uninstall";
  label: string;
  error: unknown;
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
  const [loadError, setLoadError] = useState<unknown | null>(null);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<InspectedPackage | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<DlcLifecycleItem | null>(null);
  const [removeVersionTarget, setRemoveVersionTarget] = useState<RemoveVersionTarget | null>(null);
  const [actionError, setActionError] = useState<DlcActionError | null>(null);
  const [query, setQuery] = useState("");
  const dialogOrigin = useRef<HTMLButtonElement | null>(null);
  const installButton = useRef<HTMLButtonElement | null>(null);
  const searchInput = useRef<HTMLInputElement | null>(null);

  const restoreDialogFocus = (event: Event) => {
    const origin = dialogOrigin.current;
    const target = origin?.isConnected ? origin : searchInput.current ?? installButton.current;
    if (target && !target.disabled) {
      event.preventDefault();
      target.focus();
    }
  };

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
      if (!cancelled) setLoadError(error);
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
    setActionError(null);
    try {
      const archivePath = await pickDlcPackage();
      if (!archivePath) return;
      const inspection = await inspectDlcPackage(archivePath);
      setCandidate({ archivePath, inspection });
    } catch (error) {
      setActionError({ scope: "page", label: "无法检查 DLC 安装包", error });
    } finally {
      setActionKey(null);
    }
  };

  const trustCandidate = async () => {
    if (!candidate || actionKey) return;
    setActionKey("trust");
    setActionError(null);
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
      setActionError({ scope: "inspection", label: "无法信任此发布者", error });
    } finally {
      setActionKey(null);
    }
  };

  const installCandidate = async () => {
    if (!candidate || candidate.inspection.trust_required || actionKey) return;
    setActionKey("install");
    setActionError(null);
    try {
      const installed = await installDlcPackage(candidate.archivePath);
      setPayload((current) => upsertDlc(current, installed));
      setCandidate(null);
      showToast(`${installed.display_name} 已安装，默认保持禁用`, "success");
    } catch (error) {
      setActionError({ scope: "inspection", label: "DLC 安装失败", error });
    } finally {
      setActionKey(null);
    }
  };

  const setEnabled = async (item: DlcLifecycleItem, enabled: boolean) => {
    if (actionKey) return;
    setActionKey(`${enabled ? "enable" : "disable"}:${item.dlc_id}`);
    setActionError(null);
    try {
      const updated = await setDlcEnabled(item.dlc_id, enabled);
      setPayload((current) => upsertDlc(current, updated));
      showToast(
        enabled ? `${item.display_name} 将在重启后启用` : `${item.display_name} 将在重启后停用`,
        "info",
      );
    } catch (error) {
      setActionError({
        scope: "page",
        label: enabled ? "无法启用 DLC" : "无法停用 DLC",
        error,
      });
    } finally {
      setActionKey(null);
    }
  };

  const restartNow = async () => {
    if (!desktopRuntime || actionKey) return;
    setActionKey("restart");
    setActionError(null);
    try {
      showToast("正在安全重启本地引擎并重建 DLC 运行时…", "info");
      await restartDlcRuntime();
      await refresh();
      showToast("本地引擎已重启，DLC 运行状态已刷新", "success");
    } catch (error) {
      setActionError({ scope: "page", label: "本地引擎重启失败", error });
    } finally {
      setActionKey(null);
    }
  };

  const selectVersion = async (item: DlcLifecycleItem, packageDigest: string) => {
    if (actionKey) return;
    setActionKey(`select:${item.dlc_id}:${packageDigest}`);
    setActionError(null);
    try {
      const updated = await selectDlcVersion(item.dlc_id, packageDigest);
      setPayload((current) => upsertDlc(current, updated));
      showToast(
        item.desired_enabled
          ? `${item.display_name} 已选择新包；重启后切换运行版本`
          : `${item.display_name} 已选择新包；下次启用时生效`,
        "info",
      );
    } catch (error) {
      setActionError({ scope: "page", label: "无法选择 DLC 包版本", error });
    } finally {
      setActionKey(null);
    }
  };

  const confirmRemoveVersion = async () => {
    if (!removeVersionTarget || actionKey) return;
    const { item, version } = removeVersionTarget;
    setActionKey(`remove:${item.dlc_id}:${version.package_digest}`);
    setActionError(null);
    try {
      await removeDlcVersion(item.dlc_id, version.package_digest);
      await refresh();
      setRemoveVersionTarget(null);
      showToast(`${item.display_name} ${version.version} 的旧包字节已移除`, "success");
    } catch (error) {
      setActionError({ scope: "remove", label: "无法移除旧 DLC 包版本", error });
    } finally {
      setActionKey(null);
    }
  };

  const confirmUninstall = async () => {
    if (!uninstallTarget || actionKey) return;
    setActionKey(`uninstall:${uninstallTarget.dlc_id}`);
    setActionError(null);
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
      setActionError({ scope: "uninstall", label: "DLC 卸载失败", error });
    } finally {
      setActionKey(null);
    }
  };

  const busy = actionKey !== null;
  const search = query.trim().toLowerCase();
  const visibleDlcs = payload?.dlcs.filter((item) => (
    `${item.display_name} ${item.description ?? ""} ${item.publisher} ${item.dlc_id}`.toLowerCase().includes(search)
  )) ?? [];
  return (
    <>
      <SettingsContent className="dlc-center" aria-busy={busy || (payload === null && !loadError)}>
        {restartRequired && actionKey !== "restart" ? (
          <SettingsStatus tone="warning" label="重启后应用扩展更改" description="部分扩展的启用状态或版本已更改，当前运行状态将在重启后更新。" />
        ) : null}

        {actionKey === "restart" ? (
          <SettingsStatus
            tone="loading"
            label="正在重启本地引擎"
            description="正在重新连接工作区，完成后将更新扩展状态。"
          />
        ) : null}

        {loadError ? (
          <SettingsStatus
            tone="danger"
            label="无法读取 DLC 状态"
            description={getUserErrorMessage(loadError, "无法读取 DLC 列表")}
            error={loadError}
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

        {actionError?.scope === "page" ? (
          <SettingsStatus
            tone="danger"
            label={actionError.label}
            description={getUserErrorMessage(actionError.error, `${actionError.label}，请重试`)}
            error={actionError.error}
          />
        ) : null}

        <SettingsSection
          icon={PuzzlePieceIcon}
          title="已安装扩展"
          description="按需开启工作能力，点击扩展名称查看版本与权限。"
          trailing={(
            <div className="dlc-center__primary-actions">
              {restartRequired ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!desktopRuntime || busy}
                  onClick={() => void restartNow()}
                >
                  <ArrowsClockwiseIcon size={16} aria-hidden="true" />
                  立即重启
                </Button>
              ) : null}
              <Button
                ref={installButton}
                size="sm"
                disabled={!desktopRuntime || busy}
                title={desktopRuntime ? undefined : "只能在 DBFox 桌面应用中选择安装包"}
                onClick={(event) => { dialogOrigin.current = event.currentTarget; void choosePackage(); }}
              >
                <PackageIcon size={16} aria-hidden="true" />
                {actionKey === "pick" ? "正在检查…" : "从文件安装"}
              </Button>
            </div>
          )}
        >
          {payload === null && !loadError ? (
            <div className="dlc-center__loading" role="status">
              <ArrowsClockwiseIcon className="is-spinning" size={16} aria-hidden="true" />
              正在读取已安装扩展…
            </div>
          ) : payload?.dlcs.length === 0 ? (
            <div className="dlc-center__empty">
              <CubeIcon size={20} aria-hidden="true" />
              <strong>尚未安装 DLC 扩展</strong>
              <span>选择一个签名的 .dbfox-dlc 文件；检查和安装阶段不会执行扩展代码。</span>
            </div>
          ) : (
            <>
              {payload ? (
                <div className="dlc-center__toolbar">
                  <div className="dlc-center__search" role="search">
                    <MagnifyingGlassIcon size={16} aria-hidden="true" />
                    <Input ref={searchInput} type="search" aria-label="搜索扩展" placeholder="搜索扩展…" value={query} onChange={(event) => setQuery(event.target.value)} />
                  </div>
                  <span className="dlc-center__count" role="status">{search ? `${visibleDlcs.length} / ${payload.dlcs.length}` : payload.dlcs.length} 个扩展</span>
                </div>
              ) : null}
              <div className="dlc-list">
              {visibleDlcs.map((item) => (
                <DlcRow
                  key={item.dlc_id}
                  item={item}
                  busy={busy}
                  actionKey={actionKey}
                  onSetEnabled={setEnabled}
                  onSelectVersion={selectVersion}
                  onRemoveVersion={(version, trigger) => {
                    dialogOrigin.current = trigger;
                    setActionError(null);
                    setRemoveVersionTarget({ item, version });
                  }}
                  onUninstall={(target, trigger) => {
                    dialogOrigin.current = trigger;
                    setActionError(null);
                    setUninstallTarget(target);
                  }}
                />
              ))}
              </div>
              {payload && visibleDlcs.length === 0 && search ? (
                <div className="dlc-center__empty" role="status">
                  <MagnifyingGlassIcon size={20} aria-hidden="true" />
                  <strong>未找到匹配的扩展</strong>
                  <Button variant="ghost" size="sm" onClick={() => setQuery("")}>清除搜索</Button>
                </div>
              ) : null}
            </>
          )}
        </SettingsSection>
      </SettingsContent>

      <PackageInspectionDialog
        candidate={candidate}
        actionKey={actionKey}
        actionError={actionError?.scope === "inspection" ? actionError : null}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setCandidate(null);
            setActionError(null);
          }
        }}
        onTrust={trustCandidate}
        onInstall={installCandidate}
        onCloseAutoFocus={restoreDialogFocus}
      />

      <Dialog
        open={uninstallTarget !== null}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setUninstallTarget(null);
            setActionError(null);
          }
        }}
      >
        <DialogContent className="dlc-confirm-dialog" onCloseAutoFocus={restoreDialogFocus}>
          <DialogHeader>
            <DialogTitle>卸载 {uninstallTarget?.display_name}</DialogTitle>
            <DialogDescription>
              将删除 registry 中此 DLC 的所有已安装版本和未被引用的可执行包字节。DLC 自己的数据目录默认保留，重新安装后仍可继续使用。
            </DialogDescription>
          </DialogHeader>
          <SettingsStatus
            tone="info"
            label="数据保留策略"
            description={`APP_DATA/dlcs/data/${uninstallTarget?.dlc_id ?? "<dlc_id>"}/ 不会被删除。`}
          />
          {actionError?.scope === "uninstall" ? (
            <SettingsStatus
              tone="danger"
              label={actionError.label}
              description={getUserErrorMessage(actionError.error, "DLC 卸载失败，请重试")}
              error={actionError.error}
            />
          ) : null}
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setUninstallTarget(null)}>取消</Button>
            <Button variant="destructive" disabled={busy} onClick={() => void confirmUninstall()}>
              <TrashIcon size={16} aria-hidden="true" />
              {actionKey?.startsWith("uninstall:") ? "正在卸载…" : "确认卸载"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={removeVersionTarget !== null}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setRemoveVersionTarget(null);
            setActionError(null);
          }
        }}
      >
        <DialogContent className="dlc-confirm-dialog" onCloseAutoFocus={restoreDialogFocus}>
          <DialogHeader>
            <DialogTitle>移除旧版本 {removeVersionTarget?.version.version}</DialogTitle>
            <DialogDescription>
              只删除这个未选中且未运行的包 digest。DLC 数据和历史 ToolAttempt 的原始 digest 身份不会被修改。
            </DialogDescription>
          </DialogHeader>
          <SettingsStatus
            tone="warning"
            label="包回滚不等于数据回滚"
            description="移除后不能再选择这个包；DLC-owned schema 和数据仍保持当前版本。"
          />
          {actionError?.scope === "remove" ? (
            <SettingsStatus
              tone="danger"
              label={actionError.label}
              description={getUserErrorMessage(actionError.error, "无法移除旧 DLC 包版本，请重试")}
              error={actionError.error}
            />
          ) : null}
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setRemoveVersionTarget(null)}>取消</Button>
            <Button variant="destructive" disabled={busy} onClick={() => void confirmRemoveVersion()}>
              <TrashIcon size={16} aria-hidden="true" />
              {actionKey?.startsWith("remove:") ? "正在移除…" : "确认移除旧版本"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function DlcRow({
  item,
  busy,
  actionKey,
  onSetEnabled,
  onSelectVersion,
  onRemoveVersion,
  onUninstall,
}: {
  item: DlcLifecycleItem;
  busy: boolean;
  actionKey: string | null;
  onSetEnabled: (item: DlcLifecycleItem, enabled: boolean) => Promise<void>;
  onSelectVersion: (item: DlcLifecycleItem, packageDigest: string) => Promise<void>;
  onRemoveVersion: (version: DlcInstalledVersionItem, trigger: HTMLButtonElement) => void;
  onUninstall: (item: DlcLifecycleItem, trigger: HTMLButtonElement) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const statusId = useId();
  const state = STATE_PRESENTATION[item.state];
  const uninstallAllowed = !item.desired_enabled && !item.active;
  const transitionKey = `${item.desired_enabled ? "disable" : "enable"}:${item.dlc_id}`;
  return (
    <article className="dlc-row" aria-labelledby={`dlc-${item.dlc_id}`}>
      <header className="dlc-row__header">
        <div className="dlc-row__identity">
          <span className="dlc-row__icon"><PuzzlePieceIcon size={20} aria-hidden="true" /></span>
          <div className="dlc-row__copy">
            <h3 id={`dlc-${item.dlc_id}`}>
              <button type="button" className="dlc-row__trigger" aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpanded((value) => !value)}>
                <span>{item.display_name}</span><CaretDownIcon size={16} aria-hidden="true" />
              </button>
            </h3>
            <p className="dlc-row__description" title={item.description ?? undefined}>{item.description || "此扩展未提供说明。"}</p>
            <span className="dlc-row__byline">{item.publisher} <span aria-hidden="true">·</span> <span>{item.installed_versions.length} 个版本</span></span>
          </div>
        </div>
        <span id={statusId} className={`dlc-state dlc-state--${state.tone}`}>
          {item.state === "active" ? <CheckCircleIcon size={16} aria-hidden="true" /> : null}
          {item.state === "activation_failed" ? <WarningIcon size={16} aria-hidden="true" /> : null}
          {actionKey === transitionKey ? "正在更新…" : state.label}
        </span>
        <Switch checked={item.desired_enabled} disabled={busy} aria-label={`启用 ${item.display_name}`} aria-describedby={statusId}
          onCheckedChange={(enabled) => void onSetEnabled(item, enabled)} />
      </header>

      {item.activation_failure ? (
        <Alert className="dlc-activation-error" variant="destructive">
          <WarningIcon aria-hidden="true" />
          <AlertTitle>{item.activation_failure.code}</AlertTitle>
          <AlertDescription>{item.activation_failure.message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="dlc-row__details" id={detailsId} hidden={!expanded}>{expanded ? <>
      <div className="dlc-truth-grid" role="group" aria-label="DLC 期望状态与运行状态">
        <div>
          <span>期望状态</span>
          <strong>{item.desired_enabled ? "启用" : "禁用"}</strong>
        </div>
        <div>
          <span>当前运行</span>
          <strong>{item.active ? "已激活" : "未激活"}</strong>
        </div>
        <div>
          <span>选定包指纹</span>
          <code title={item.selected_digest}>{shortDigest(item.selected_digest)}</code>
        </div>
        <div>
          <span>运行包指纹</span>
          <code title={item.active_digest ?? undefined}>{shortDigest(item.active_digest)}</code>
        </div>
      </div>

      <dl className="dlc-row__metadata">
        <div><dt>ID / 版本</dt><dd><code>{item.dlc_id}</code> · {item.version}</dd></div>
        <div><dt>发布者</dt><dd>{item.publisher} · <code title={item.publisher_fingerprint ?? undefined}>{shortDigest(item.publisher_fingerprint)}</code></dd></div>
        <div><dt>运行组件</dt><dd>{[
          item.backend_entrypoint_present ? "后端" : null,
          item.frontend_entrypoint_present ? "界面" : null,
        ].filter(Boolean).join(" + ") || "无可用入口"}</dd></div>
      </dl>

      <div className="dlc-versions" role="group" aria-label="已安装 DLC 包版本">
        <div className="dlc-versions__heading">
          <strong>已安装版本（{item.installed_versions.length}）</strong>
          <span>版本切换在重启后生效，不会回退已有数据格式。</span>
        </div>
        <ul>
          {item.installed_versions.map((version) => {
            const selectKey = `select:${item.dlc_id}:${version.package_digest}`;
            return (
              <li key={version.package_digest}>
                <div className="dlc-version__identity">
                  <strong>{version.version}</strong>
                  <code title={version.package_digest}>{shortDigest(version.package_digest)}</code>
                </div>
                <div className="dlc-version__states">
                  {version.selected ? <span>已选择</span> : null}
                  {version.active ? <span>运行中</span> : null}
                  {version.pending ? <span>待重启</span> : null}
                </div>
                <div className="dlc-version__actions">
                  {!version.selected ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => void onSelectVersion(item, version.package_digest)}
                    >
                      <ArrowsLeftRightIcon size={16} aria-hidden="true" />
                      {actionKey === selectKey ? "正在切换…" : "切换版本"}
                    </Button>
                  ) : null}
                  {!version.selected ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy || !version.removable}
                      title={version.removable ? "移除此旧版本包" : "当前运行版本必须在重启切换后才能移除"}
                      onClick={(event) => onRemoveVersion(version, event.currentTarget)}
                    >
                      <TrashIcon size={16} aria-hidden="true" />
                      移除旧版本
                    </Button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <details className="dlc-permissions">
        <summary><CaretDownIcon size={16} aria-hidden="true" />权限声明（{item.permissions.length}）</summary>
        {item.permissions.length > 0 ? (
          <ul>{item.permissions.map((permission) => <li key={permission}><code>{permission}</code></li>)}</ul>
        ) : <p>未声明额外权限。</p>}
      </details>

      <footer className="dlc-row__actions">
        <Button
          variant="ghost"
          size="sm"
          disabled={busy || !uninstallAllowed}
          title={uninstallAllowed ? "卸载并保留 DLC 数据" : "请先停用并重启，确认当前运行状态为未激活"}
          onClick={(event) => onUninstall(item, event.currentTarget)}
        >
          <TrashIcon size={16} aria-hidden="true" />
          卸载
        </Button>
        {!uninstallAllowed ? <span className="dlc-row__constraint">停用并重启后才可卸载</span> : null}
      </footer>
      </> : null}</div>
    </article>
  );
}

function PackageInspectionDialog({
  candidate,
  actionKey,
  actionError,
  onOpenChange,
  onTrust,
  onInstall,
  onCloseAutoFocus,
}: {
  candidate: InspectedPackage | null;
  actionKey: string | null;
  actionError: DlcActionError | null;
  onOpenChange: (open: boolean) => void;
  onTrust: () => Promise<void>;
  onInstall: () => Promise<void>;
  onCloseAutoFocus: (event: Event) => void;
}) {
  const inspection = candidate?.inspection;
  const busy = actionKey === "trust" || actionKey === "install";
  return (
    <Dialog open={candidate !== null} onOpenChange={onOpenChange}>
      <DialogContent
        className="dlc-inspection-dialog"
        onCloseAutoFocus={onCloseAutoFocus}
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
              <PuzzlePieceIcon size={20} aria-hidden="true" />
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
                meta={<ShieldWarningIcon size={16} aria-hidden="true" />}
              />
            ) : (
              <SettingsStatus
                tone="success"
                label="发布者公钥已受信任"
                description="安装仍默认为禁用；启用并重启前不会执行扩展代码。"
                meta={<ShieldCheckIcon size={16} aria-hidden="true" />}
              />
            )}
            {actionError ? (
              <SettingsStatus
                tone="danger"
                label={actionError.label}
                description={getUserErrorMessage(actionError.error, `${actionError.label}，请重试`)}
                error={actionError.error}
              />
            ) : null}
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>取消</Button>
          {inspection?.trust_required ? (
            <Button disabled={busy} onClick={() => void onTrust()}>
              <ShieldCheckIcon size={16} aria-hidden="true" />
              {actionKey === "trust" ? "正在重新验证…" : "信任此发布者"}
            </Button>
          ) : (
            <Button disabled={busy || !inspection} onClick={() => void onInstall()}>
              <PackageIcon size={16} aria-hidden="true" />
              {actionKey === "install" ? "正在安装…" : "安装（默认禁用）"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
