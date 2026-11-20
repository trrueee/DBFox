import { useEffect, useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowsClockwiseIcon, EyeIcon, MonitorIcon, PlusIcon, ShieldCheckIcon } from "@/components/icons";
import { Button, ErrorState, LoadingState } from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import { computerSharesQuery, computerTargetsQuery, previewComputer, readBrowserState, shareComputer, stopAllComputer, stopComputer, COMPUTER_RESOURCE_KIND } from "../../lib/api/computer";
import type { ComputerGrant, ShareInput } from "../../lib/api/generated/types.gen";
import { selectActiveConversationId, selectActiveWorkbench, useWorkspaceStore } from "../../stores/workspaceStore";
import { CaptureImage } from "./CaptureImage";
import { getDesktopEngineStatus } from "../../lib/desktopHost";
import { openComputerDock } from "./openComputerDock";
import "./computer.css";

const STATUS = { active: "共享中", paused: "已停止 · 可人工接管", revoked: "已结束共享", interrupted: "重启后已中断", expired: "共享已到期" } as const;

export function ComputerDock({ conversationId }: { conversationId: string }) {
  const shares = useQuery(computerSharesQuery(conversationId));
  const shortcut = useQuery({ queryKey: ["computer-stop-shortcut"], queryFn: getDesktopEngineStatus, staleTime: Infinity, retry: false });
  const [choosing, setChoosing] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 5000); return () => window.clearInterval(timer); }, []);
  const selected = shares.data?.find(grant => grant.id === selectedId)
    ?? shares.data?.find(grant => grant.status === "active") ?? shares.data?.[0];
  const active = selected?.status === "active" && selected.expires_at > now;
  const client = useQueryClient();
  const activeShares = shares.data?.filter(grant => grant.status === "active" && grant.expires_at > now) ?? [];
  const stopAll = useMutation({ mutationFn: stopAllComputer,
    onSuccess: () => client.invalidateQueries({ queryKey: ["computer-shares"] }) });
  const stop = useMutation({
    mutationFn: ({ grant, revoke }: { grant: ComputerGrant; revoke?: boolean }) => stopComputer(conversationId, grant.id, revoke),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: computerSharesQuery(conversationId).queryKey }); },
  });
  const choose = (grant: ComputerGrant) => {
    setSelectedId(grant.id); setChoosing(false);
    if (grant.status === "active" && grant.expires_at > now) openComputerDock(conversationId, grant);
  };

  return <section className="computer-dock" aria-label="电脑工作台">
    {activeShares.length > 0 && <div className="computer-takeover" role="region" aria-label="电脑停止控制">
      <span>{activeShares.length} 个目标共享中</span><Button variant="destructive" size="sm" disabled={stopAll.isPending}
        onClick={() => stopAll.mutate()}>全部停止并接管</Button>
      {stopAll.isError && <p role="alert">{getUserErrorMessage(stopAll.error, "停止尚未获确认，请重试。")}</p>}
    </div>}
    <header className="computer-header">
      <div className="computer-header__icon"><MonitorIcon size={22} aria-hidden="true" /></div>
      <div><h2>让 Agent 看见并操作</h2><p>选择一个目标，保持随时可接管。</p></div>
    </header>
    {shares.isPending ? <LoadingState label="正在检查共享目标" /> : shares.isError ? <ErrorState title="共享状态不可用"
      description={getUserErrorMessage(shares.error)} onRetry={() => void shares.refetch()} /> : <>
      {Boolean(shares.data?.length) && <div className="computer-targets" aria-label="共享目标">
        {shares.data?.slice(0, 8).map(grant => <button type="button" key={grant.id} className="computer-target"
          aria-pressed={selected?.id === grant.id} onClick={() => choose(grant)}>
          <MonitorIcon size={18} aria-hidden="true" /><span>{grant.target.title}</span>
          <small>{STATUS[grant.expires_at <= now && ["active", "paused"].includes(grant.status) ? "expired" : grant.status]}</small>
        </button>)}
      </div>}
      {selected && !choosing ? <>
        <div className="computer-summary">
          <div className="computer-summary__status" data-active={active || undefined}><span aria-hidden="true" />{STATUS[!active && selected.status === "active" ? "expired" : selected.status]}</div>
          <h3>{selected.target.title}</h3>
          <p>{selected.permission === "control" ? "观察与控制 · 每次操作单独审批" : "仅观察 · 无法点击或输入"}</p>
          <p>{active ? `剩余约 ${Math.max(1, Math.ceil((selected.expires_at - now) / 60000))} 分钟` : "继续工作需要重新共享并观察。"}</p>
          <div className="computer-actions">
            {active && <Button variant="destructive" size="sm" disabled={stop.isPending}
              onClick={() => stop.mutate({ grant: selected })}>停止并接管</Button>}
            {["active", "paused"].includes(selected.status) && <Button variant="ghost" size="sm" disabled={stop.isPending}
              onClick={() => stop.mutate({ grant: selected, revoke: true })}>结束共享</Button>}
            <Button variant="outline" size="sm" disabled={stop.isPending} onClick={() => setChoosing(true)}><PlusIcon size={16} aria-hidden="true" />{active ? "共享其他目标" : "重新共享"}</Button>
          </div>
          {stop.isError && <p role="alert" className="computer-error">{getUserErrorMessage(stop.error, "停止未获确认，请重试。")}<Button variant="link" size="sm" onClick={() => stop.reset()}>收起</Button></p>}
        </div>
        {active && selected.target.kind === "browser" && <BrowserDetails conversationId={conversationId} grant={selected} />}
        {active ? <ComputerPreview key={selected.id} conversationId={conversationId} grant={selected} />
          : <div className="computer-empty"><ShieldCheckIcon size={22} aria-hidden="true" /><p>当前没有可执行的共享</p><span>停止后的窗口不会自动恢复控制；受控浏览器会关闭。</span></div>}
      </> : <ShareComputerForm conversationId={conversationId} grants={shares.data ?? []} now={now} onCancel={selected ? () => setChoosing(false) : undefined}
        onShared={grant => { choose(grant); }} />}
    </>}
    <footer className="computer-footnote"><ShieldCheckIcon size={16} aria-hidden="true" /><p>共享仅用于此对话。关闭面板不会结束共享。<br />{shortcut.data?.computerStopShortcut ? <>紧急停止：<kbd>Ctrl</kbd> + <kbd>Alt</kbd> + <kbd>Shift</kbd> + <kbd>Esc</kbd></> : "全局停止快捷键不可用，请使用面板中的停止按钮。"}</p></footer>
  </section>;
}

function BrowserDetails({ conversationId, grant }: { conversationId: string; grant: ComputerGrant }) {
  const state = useQuery({ queryKey: ["computer-browser", conversationId, grant.id], retry: false, refetchInterval: 3000,
    queryFn: ({ signal }) => readBrowserState(conversationId, grant.id, signal) });
  if (!state.data) return state.isError ? <p role="status" className="computer-error">浏览器状态暂不可用，请刷新画面或停止共享。</p> : null;
  return <section className="computer-browser" aria-label="浏览器状态"><p className="computer-address" title={state.data.url}>{state.data.url}</p>
    <ul aria-label="受控页面">{state.data.tabs.map(tab => <li key={tab.id} aria-current={tab.id === state.data.current_tab_id ? "page" : undefined}>
      {tab.title || "空白页面"}{tab.id === state.data.current_tab_id ? " · 当前" : ""}</li>)}</ul></section>;
}

function ComputerPreview({ conversationId, grant }: { conversationId: string; grant: ComputerGrant }) {
  const preview = useQuery({ queryKey: ["computer-preview", conversationId, grant.id], retry: false, staleTime: Infinity, gcTime: 0,
    queryFn: ({ signal }) => previewComputer(conversationId, grant.id, signal) });
  return <figure className="computer-preview">
    <figcaption><span><EyeIcon size={16} aria-hidden="true" />画面预览</span><Button variant="ghost" size="sm" disabled={preview.isFetching}
      onClick={() => void preview.refetch()} aria-label="刷新画面"><ArrowsClockwiseIcon size={16} aria-hidden="true" />刷新</Button></figcaption>
    {preview.isPending ? <LoadingState label="正在读取目标画面" /> : preview.isError ? <ErrorState title="画面暂不可用"
      description={getUserErrorMessage(preview.error)} onRetry={() => void preview.refetch()} /> : preview.data ? <CaptureImage image={preview.data} alt={`${grant.target.title}的画面预览`} /> : null}
    <p>{preview.isFetching ? "正在刷新…" : preview.dataUpdatedAt ? `采集于 ${new Date(preview.dataUpdatedAt).toLocaleTimeString()} · 预览不会触发操作` : ""}</p>
  </figure>;
}

function ShareComputerForm({ conversationId, grants, now, onShared, onCancel }: {
  conversationId: string; grants: ComputerGrant[]; now: number; onShared: (grant: ComputerGrant) => void; onCancel?: () => void;
}) {
  const id = useId();
  const targets = useQuery(computerTargetsQuery);
  const [kind, setKind] = useState<"browser" | "window">("browser");
  const [targetId, setTargetId] = useState("");
  const [permission, setPermission] = useState<"observe" | "control">("observe");
  const [duration, setDuration] = useState<5 | 15 | 30>(15);
  const [replace, setReplace] = useState(false);
  const candidates = targets.data?.filter(option => option.target.kind === kind) ?? [];
  const selected = candidates.find(option => option.inventory_id === targetId) ?? (kind === "browser" ? candidates[0] : undefined);
  const previous = grants.some(grant => grant.target.kind === kind && ["active", "paused"].includes(grant.status) && grant.expires_at > now);
  const client = useQueryClient();
  const share = useMutation({
    mutationFn: (input: ShareInput) => shareComputer(conversationId, input),
    onSuccess: async grant => {
      await client.invalidateQueries({ queryKey: computerSharesQuery(conversationId).queryKey });
      // This panel reflects its own acknowledged share even when a restored
      // Dock belongs to another conversation. Only the active input gets refs.
      onShared(grant);
      const state = useWorkspaceStore.getState();
      const workbench = selectActiveWorkbench(state);
      const activeId = selectActiveConversationId(state) ?? workbench.draftConversationId;
      if (activeId !== conversationId) return;
      state.addWorkbenchReference({ label: grant.target.title, object: { kind: COMPUTER_RESOURCE_KIND, id: grant.id, version: grant.version } });
    },
  });
  return <form className="computer-share" onSubmit={event => {
    event.preventDefault();
    if (selected) share.mutate({ inventory_id: selected.inventory_id, permission, duration_minutes: duration, replace_existing: previous && replace });
  }}>
    <div className="computer-segment" role="group" aria-label="目标类型">
      <button type="button" aria-pressed={kind === "browser"} onClick={() => { setKind("browser"); setTargetId(""); setReplace(false); }}>受控浏览器</button>
      <button type="button" aria-pressed={kind === "window"} onClick={() => { setKind("window"); setTargetId(""); setReplace(false); }}>共享窗口</button>
    </div>
    <div className="computer-share__intro"><h3>{kind === "browser" ? "一个独立的浏览器空间" : "只共享你选择的窗口"}</h3>
      <p>{kind === "browser" ? "使用 Microsoft Edge，不继承个人登录信息。需要登录时可由你手动接管。" : "包括该程序的所属对话框。仅支持当前用户的普通窗口，敏感输入由你接管。"}</p></div>
    {targets.isPending ? <LoadingState label="正在发现可用目标" /> : targets.isError ? <ErrorState title="目标列表不可用"
      description={getUserErrorMessage(targets.error)} onRetry={() => void targets.refetch()} /> : <>
      <label className="computer-field" htmlFor={`${id}-target`}>共享目标
        <select id={`${id}-target`} value={selected?.inventory_id ?? ""} onChange={event => setTargetId(event.target.value)} disabled={share.isPending}>
          <option value="" disabled>{kind === "browser" ? "未找到 Microsoft Edge" : "选择具体窗口"}</option>
          {candidates.map(option => <option key={option.inventory_id} value={option.inventory_id}>{option.target.title}</option>)}
        </select>
      </label>
      <Button type="button" variant="link" size="sm" disabled={targets.isFetching || share.isPending} onClick={() => void targets.refetch()}><ArrowsClockwiseIcon size={16} aria-hidden="true" />刷新目标列表</Button>
    </>}
    <fieldset className="computer-permissions" disabled={share.isPending}><legend>允许 Agent 做什么</legend>
      <label data-selected={permission === "observe" || undefined}><input type="radio" name={`${id}-permission`} checked={permission === "observe"} onChange={() => setPermission("observe")} /><span><strong>仅观察</strong><small>读取画面与可访问元素</small></span></label>
      <label data-selected={permission === "control" || undefined}><input type="radio" name={`${id}-permission`} checked={permission === "control"} onChange={() => setPermission("control")} /><span><strong>观察与控制</strong><small>点击、输入等操作仍逐次审批</small></span></label>
    </fieldset>
    <label className="computer-field" htmlFor={`${id}-duration`}>共享期限<select id={`${id}-duration`} value={duration} disabled={share.isPending}
      onChange={event => setDuration(Number(event.target.value) as 5 | 15 | 30)}><option value={5}>5 分钟</option><option value={15}>15 分钟</option><option value={30}>30 分钟</option></select></label>
    {previous && <label className="computer-replace"><input type="checkbox" checked={replace} onChange={event => setReplace(event.target.checked)} disabled={share.isPending} />结束并替换此对话原有的同类共享</label>}
    {share.isError && <p role="alert" className="computer-error">{getUserErrorMessage(share.error, "共享未获确认。请先刷新共享状态，再决定是否重试。")}</p>}
    <div className="computer-actions"><Button type="submit" disabled={!selected || share.isPending || (previous && !replace)}>{share.isPending ? "正在建立共享…" : "开始共享"}</Button>
      {onCancel && <Button type="button" variant="ghost" disabled={share.isPending} onClick={onCancel}>取消</Button>}</div>
    <p className="computer-hint">需要支持图片的模型。画面会发送给当前模型，请先关闭目标内不希望分享的内容。</p>
  </form>;
}
