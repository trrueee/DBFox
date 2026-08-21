import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  HelpCircle,
  MoreHorizontal,
  PanelRightClose,
  PanelRightOpen,
  X,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "../../components/ui";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import type { WorkspaceDockTab } from "../../types/workspace";
import type { DockViewRegistry } from "../dock/dockViewComposition";
import { DEFAULT_REGISTRY, dockViewTitle } from "../dock/dockViewComposition";
import { useDlcStore } from "../dlc/extensionStore";
import type { DockViewContribution } from "../dock/types";
import { clearCspFlexBasis, setCspFlexBasis } from "../../lib/cspVirtualLayout";
import "./WorkspaceDock.css";

export interface WorkspaceDockProps {
  activeDatasourceId?: string;
  activeConversationId: string | null;
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
  registry?: DockViewRegistry;
}

const DOCK_MIN_WIDTH_PX = 320;
const DOCK_MAX_WIDTH_RATIO = 0.56;
const OVERFLOW_TRIGGER_RESERVE_PX = 30;

export interface DockTabWindow {
  start: number;
  end: number;
}

/**
 * Plans which tabs are directly visible in the tab strip. Tabs outside the
 * returned window are reachable through the overflow menu. The active tab is
 * always kept inside the window; when it would overflow, the window slides so
 * the active tab becomes its last entry.
 */
export function planDockTabWindow(
  widths: readonly number[],
  availableWidth: number,
  activeIndex: number,
  reservePx: number = OVERFLOW_TRIGGER_RESERVE_PX,
): DockTabWindow {
  const total = widths.length;
  if (total === 0 || availableWidth <= 0) return { start: 0, end: total };
  const limit = Math.max(0, availableWidth - reservePx);
  let used = 0;
  let end = 0;
  while (end < total && used + widths[end] <= limit) {
    used += widths[end];
    end += 1;
  }
  if (end >= total) return { start: 0, end: total };
  const anchor = Math.min(Math.max(activeIndex, 0), total - 1);
  if (anchor < end) return { start: 0, end: Math.max(end, 1) };
  end = anchor + 1;
  let start = end;
  used = 0;
  while (start > 0 && used + widths[start - 1] <= limit) {
    start -= 1;
    used += widths[start];
  }
  // The anchor itself is always visible, even if it alone exceeds the limit.
  if (start >= end) start = end - 1;
  return { start, end };
}

function resolveDockView(
  viewType: string,
  registry: DockViewRegistry,
  dlcDockViews: readonly DockViewContribution[],
) {
  return registry.get(viewType) ?? dlcDockViews.find((view) => view.viewType === viewType) ?? null;
}

function dockTabIcon(
  tab: WorkspaceDockTab,
  registry: DockViewRegistry,
  dlcDockViews: readonly DockViewContribution[],
) {
  return resolveDockView(tab.viewType, registry, dlcDockViews)?.icon(tab)
    ?? <HelpCircle size={13} aria-hidden="true" />;
}

export function WorkspaceDock({
  activeDatasourceId = "",
  activeConversationId,
  showToast,
  registry = DEFAULT_REGISTRY,
}: WorkspaceDockProps) {
  const dock = useWorkspaceStore((s) => s.dock);
  const dockTabs = useWorkspaceStore((s) => s.dockTabs);
  const setDockOpen = useWorkspaceStore((s) => s.setDockOpen);
  const setDockActiveTab = useWorkspaceStore((s) => s.setDockActiveTab);
  const closeDockTab = useWorkspaceStore((s) => s.closeDockTab);
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  // Subscribe so active runtime contributions are reflected in production Dock consumers.
  const dlcDockViews = useDlcStore((s) => s.contributions.dockViews);

  const visibleTabs = useMemo(() => {
    return dockTabs.filter((tab) => {
      const contribution = resolveDockView(tab.viewType, registry, dlcDockViews);
      if (!contribution) {
        // Unknown viewType fallback: visible so it can be viewed and closed
        return true;
      }
      return contribution.isVisible(tab, {
        activeProjectId,
        activeDatasourceId,
        activeConversationId,
      });
    });
  }, [activeConversationId, activeDatasourceId, activeProjectId, dlcDockViews, dockTabs, registry]);

  const activeKey = dock.activeViewKey;
  const activeTab =
    visibleTabs.find((tab) => tab.viewKey === activeKey) ?? visibleTabs.at(-1) ?? null;

  // ── Tab strip windowing: direct tabs + overflow menu (no hidden scrollbar) ──
  const tabsRef = useRef<HTMLDivElement>(null);
  const tabWidthsRef = useRef(new Map<string, number>());
  const [tabWindow, setTabWindow] = useState<DockTabWindow | null>(null);
  const activeTabIndex = Math.max(
    0,
    visibleTabs.findIndex((tab) => tab.viewKey === activeTab?.viewKey),
  );

  const recomputeTabWindow = useCallback(() => {
    const container = tabsRef.current;
    if (!container || container.clientWidth <= 0) {
      setTabWindow((prev) => (prev === null ? prev : null));
      return;
    }
    const widths = visibleTabs.map((tab) => tabWidthsRef.current.get(tab.viewKey) ?? 0);
    const next = planDockTabWindow(widths, container.clientWidth, activeTabIndex);
    setTabWindow((prev) => (prev && prev.start === next.start && prev.end === next.end ? prev : next));
  }, [activeTabIndex, visibleTabs]);

  useLayoutEffect(() => {
    recomputeTabWindow();
    const container = tabsRef.current;
    if (!container || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(recomputeTabWindow);
    observer.observe(container);
    return () => observer.disconnect();
  }, [recomputeTabWindow]);

  const registerTabNode = useCallback((viewKey: string) => (node: HTMLElement | null) => {
    if (!node) return;
    const measured = node.offsetWidth;
    if (measured > 0) tabWidthsRef.current.set(viewKey, measured);
  }, []);

  const resolvedWindow = tabWindow ?? { start: 0, end: visibleTabs.length };
  const directTabs = visibleTabs.slice(resolvedWindow.start, resolvedWindow.end);
  const overflowTabs = [
    ...visibleTabs.slice(0, resolvedWindow.start),
    ...visibleTabs.slice(resolvedWindow.end),
  ];

  // ── Subtle resizer: drag the left edge; keyboard adjustable ──
  const [dockWidth, setDockWidth] = useState<number | null>(null);
  const [resizing, setResizing] = useState(false);
  const resizeDragRef = useRef<{ pointerId: number; startClientX: number; startWidth: number } | null>(null);
  const widthToken = useId().replace(/[^a-zA-Z0-9_-]/g, "");

  useEffect(() => {
    setCspFlexBasis(widthToken, dockWidth);
    return () => clearCspFlexBasis(widthToken);
  }, [dockWidth, widthToken]);

  const clampDockWidth = useCallback((width: number) => {
    const stageWidth = tabsRef.current?.closest("aside")?.parentElement?.clientWidth ?? 0;
    const maxWidth = stageWidth > 0 ? Math.floor(stageWidth * DOCK_MAX_WIDTH_RATIO) : Number.POSITIVE_INFINITY;
    return Math.min(Math.max(Math.round(width), DOCK_MIN_WIDTH_PX), Math.max(DOCK_MIN_WIDTH_PX, maxWidth));
  }, []);

  const handleResizerPointerDown = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (dockWidth === null) {
      setDockWidth(clampDockWidth(event.currentTarget.parentElement?.offsetWidth ?? 440));
    }
    resizeDragRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startWidth: event.currentTarget.parentElement?.offsetWidth ?? 440,
    };
    setResizing(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }, [clampDockWidth, dockWidth]);

  const handleResizerPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = resizeDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const delta = drag.startClientX - event.clientX;
    setDockWidth(clampDockWidth(drag.startWidth + delta));
  }, [clampDockWidth]);

  const handleResizerPointerEnd = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (resizeDragRef.current?.pointerId === event.pointerId) {
      resizeDragRef.current = null;
      setResizing(false);
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const handleResizerKeyDown = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 48 : 16;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const current = dockWidth ?? event.currentTarget.parentElement?.offsetWidth ?? 440;
    const delta = event.key === "ArrowLeft" ? step : -step;
    setDockWidth(clampDockWidth(current + delta));
  }, [clampDockWidth, dockWidth]);

  if (!dock.open) {
    return (
      <aside className="workspace-dock workspace-dock--collapsed" aria-label="工作台 Dock">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="workspace-dock__expand"
              onClick={() => setDockOpen(true)}
              aria-label="展开工作台 Dock"
            >
              <PanelRightOpen size={16} aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent>展开工作台</TooltipContent>
        </Tooltip>
        {visibleTabs.slice(0, 4).map((tab) => (
          <Tooltip key={tab.viewKey}>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="workspace-dock__rail-item"
                aria-label={dockViewTitle(tab, registry)}
                onClick={() => setDockActiveTab(tab.viewKey)}
              >
                {dockTabIcon(tab, registry, dlcDockViews)}
              </button>
            </TooltipTrigger>
            <TooltipContent>{tab.title}</TooltipContent>
          </Tooltip>
        ))}
      </aside>
    );
  }

  return (
    <aside
      className="workspace-dock"
      aria-label="工作台 Dock"
      data-csp-flex-basis={widthToken}
    >
      <div
        className="workspace-dock__resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整工作台宽度"
        aria-valuenow={dockWidth ?? undefined}
        data-resizing={resizing ? "true" : undefined}
        onPointerDown={handleResizerPointerDown}
        onPointerMove={handleResizerPointerMove}
        onPointerUp={handleResizerPointerEnd}
        onPointerCancel={handleResizerPointerEnd}
        onKeyDown={handleResizerKeyDown}
        tabIndex={0}
      />
      <header className="workspace-dock__tabbar">
        <div className="workspace-dock__tabs" role="tablist" aria-label="工作台标签" ref={tabsRef}>
          {directTabs.map((tab) => {
            const active = tab.viewKey === activeTab?.viewKey;
            return (
              <div
                key={tab.viewKey}
                ref={registerTabNode(tab.viewKey)}
                className={`workspace-dock__tab ${active ? "is-active" : ""}`}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className="workspace-dock__tab-main"
                  title={tab.title}
                  onClick={() => setDockActiveTab(tab.viewKey)}
                >
                  <span className="workspace-dock__tab-icon" aria-hidden="true">
                    {dockTabIcon(tab, registry, dlcDockViews)}
                  </span>
                  <span className="workspace-dock__tab-title">{tab.title}</span>
                </button>
                {tab.closeable && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        className="workspace-dock__tab-close"
                        aria-label={`关闭 ${tab.title}`}
                        onClick={() => closeDockTab(tab.viewKey)}
                      >
                        <X size={11} aria-hidden="true" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent>关闭 {tab.title}</TooltipContent>
                  </Tooltip>
                )}
              </div>
            );
          })}
          {overflowTabs.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="workspace-dock__overflow"
                  aria-label={`更多标签（${overflowTabs.length} 个）`}
                >
                  <MoreHorizontal size={15} aria-hidden="true" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {overflowTabs.map((tab) => (
                  <DropdownMenuItem key={tab.viewKey} onClick={() => setDockActiveTab(tab.viewKey)}>
                    {tab.title}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="workspace-dock__collapse"
              onClick={() => setDockOpen(false)}
              aria-label="收起工作台 Dock"
            >
              <PanelRightClose size={15} aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent>收起工作台</TooltipContent>
        </Tooltip>
      </header>
      <div className="workspace-dock__content" key={activeTab?.viewKey ?? "empty"}>
        {renderDockTab(
          activeTab,
          activeProjectId,
          activeDatasourceId,
          activeConversationId,
          showToast,
          registry,
          dlcDockViews,
        )}
      </div>
    </aside>
  );
}

function renderDockTab(
  tab: WorkspaceDockTab | null,
  activeProjectId: string,
  activeDatasourceId: string,
  activeConversationId: string | null,
  showToast: WorkspaceDockProps["showToast"],
  registry: DockViewRegistry,
  dlcDockViews: readonly DockViewContribution[],
) {
  if (!tab) {
    return (
      <EmptyState
        title="没有打开的标签"
        description="从左侧资源或对话打开对象后，会在这里继续查看和操作。"
      />
    );
  }

  const contribution = resolveDockView(tab.viewType, registry, dlcDockViews);
  if (!contribution) {
    return (
      <EmptyState
        title="未知视图"
        description={`该 Dock 视图类型暂无渲染器：${tab.viewType}`}
      />
    );
  }
  return (
    <div key={tab.viewKey}>
      {contribution.render(tab, {
        activeProjectId,
        activeDatasourceId,
        activeConversationId,
        showToast,
        onOpenQueryResult: (query) =>
          useWorkspaceStore.getState().showSmartQueryHome(query),
      })}
    </div>
  );
}
