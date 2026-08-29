import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  HelpCircle,
  Maximize2,
  MoreHorizontal,
  Minimize2,
  PanelRightClose,
  PanelRightOpen,
  X,
} from "lucide-react";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "../../components/ui";
import {
  selectActiveDockOpen,
  selectActiveDockTabs,
  selectActiveDockViewKey,
  selectActiveWorkbenchScopeId,
  useWorkspaceStore,
} from "../../stores/workspaceStore";
import type { WorkspaceDockTab } from "../../types/workspace";
import type { DockViewRegistry } from "../dock/dockViewComposition";
import { DEFAULT_REGISTRY, dockViewTitle } from "../dock/dockViewComposition";
import { useDlcStore } from "../dlc/extensionStore";
import type { DockViewContribution } from "../dock/types";
import type { WorkbenchReference } from "../../types/workspace";
import "./WorkspaceDock.css";

export interface WorkspaceDockProps {
  activeConversationId: string | null;
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
  registry?: DockViewRegistry;
}

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
    ?? <HelpCircle size={14} aria-hidden="true" />;
}

export function WorkspaceDock({
  activeConversationId,
  showToast,
  registry = DEFAULT_REGISTRY,
}: WorkspaceDockProps) {
  const dockOpen = useWorkspaceStore(selectActiveDockOpen);
  const dockTabs = useWorkspaceStore(selectActiveDockTabs);
  const activeViewKey = useWorkspaceStore(selectActiveDockViewKey);
  const workbenchScopeId = useWorkspaceStore(selectActiveWorkbenchScopeId);
  const addWorkbenchReference = useWorkspaceStore((s) => s.addWorkbenchReference);
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
        activeConversationId,
      });
    });
  }, [activeConversationId, activeProjectId, dlcDockViews, dockTabs, registry]);

  const activeKey = activeViewKey;
  const activeTab =
    visibleTabs.find((tab) => tab.viewKey === activeKey) ?? visibleTabs.at(-1) ?? null;

  // ── Tab strip windowing: direct tabs + overflow menu (no hidden scrollbar) ──
  const tabsRef = useRef<HTMLDivElement>(null);
  const tabWidthsRef = useRef(new Map<string, number>());
  const tabTriggerRefs = useRef(new Map<string, HTMLButtonElement>());
  const overflowTriggerRef = useRef<HTMLButtonElement>(null);
  const collapseButtonRef = useRef<HTMLButtonElement>(null);
  const restoreFocusAfterCloseRef = useRef(false);
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

  const registerTabTrigger = useCallback((viewKey: string) => (node: HTMLButtonElement | null) => {
    if (node) tabTriggerRefs.current.set(viewKey, node);
    else tabTriggerRefs.current.delete(viewKey);
  }, []);

  const resolvedWindow = tabWindow ?? { start: 0, end: visibleTabs.length };
  const directTabs = visibleTabs.slice(resolvedWindow.start, resolvedWindow.end);
  const overflowTabs = useMemo(() => [
    ...visibleTabs.slice(0, resolvedWindow.start),
    ...visibleTabs.slice(resolvedWindow.end),
  ], [resolvedWindow.end, resolvedWindow.start, visibleTabs]);

  useLayoutEffect(() => {
    if (!restoreFocusAfterCloseRef.current) return;
    const activeTrigger = activeTab ? tabTriggerRefs.current.get(activeTab.viewKey) : null;
    if (activeTrigger) {
      activeTrigger.focus();
      restoreFocusAfterCloseRef.current = false;
      return;
    }
    if (activeTab && overflowTabs.some((tab) => tab.viewKey === activeTab.viewKey)) {
      // The active window is recalculated in the preceding layout effect. Keep
      // the pending target until its real Radix trigger has mounted.
      overflowTriggerRef.current?.focus();
      return;
    }
    collapseButtonRef.current?.focus();
    restoreFocusAfterCloseRef.current = false;
  }, [activeTab, directTabs, overflowTabs]);

  const handleCloseTab = (viewKey: string) => {
    restoreFocusAfterCloseRef.current = true;
    closeDockTab(viewKey);
  };

  const [fullscreen, setFullscreen] = useState(false);

  if (!dockOpen) {
    return (
      <aside className="workspace-dock workspace-dock--collapsed" aria-label="工作区">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              className="workspace-dock__expand"
              onClick={() => setDockOpen(true)}
              aria-label="展开工作区"
            >
              <PanelRightOpen size={16} aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>展开工作区</TooltipContent>
        </Tooltip>
        {visibleTabs.slice(0, 4).map((tab) => (
          <Tooltip key={tab.viewKey}>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                className="workspace-dock__rail-item"
                aria-label={dockViewTitle(tab, registry)}
                onClick={() => setDockActiveTab(tab.viewKey)}
              >
                {dockTabIcon(tab, registry, dlcDockViews)}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{tab.title}</TooltipContent>
          </Tooltip>
        ))}
      </aside>
    );
  }

  return (
    <Tabs value={activeTab?.viewKey ?? ""} onValueChange={setDockActiveTab} asChild>
      <aside
      className="workspace-dock"
      aria-label="工作区"
      data-fullscreen={fullscreen ? "true" : undefined}
    >
      <header className="workspace-dock__tabbar">
        <TabsList className="workspace-dock__tabs" aria-label="工作区标签" ref={tabsRef}>
          {directTabs.map((tab) => {
            const active = tab.viewKey === activeTab?.viewKey;
            return (
              <div
                key={tab.viewKey}
                ref={registerTabNode(tab.viewKey)}
                className={`workspace-dock__tab ${active ? "is-active" : ""}`}
              >
                <TabsTrigger
                  ref={registerTabTrigger(tab.viewKey)}
                  value={tab.viewKey}
                  className="workspace-dock__tab-main"
                  title={tab.title}
                  onClick={() => setDockActiveTab(tab.viewKey)}
                >
                  <span className="workspace-dock__tab-icon" aria-hidden="true">
                    {dockTabIcon(tab, registry, dlcDockViews)}
                  </span>
                  <span className="workspace-dock__tab-title">{tab.title}</span>
                </TabsTrigger>
                {tab.closeable && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        className="workspace-dock__tab-close"
                        aria-label={`关闭 ${tab.title}`}
                        onClick={() => handleCloseTab(tab.viewKey)}
                      >
                        <X size={14} aria-hidden="true" />
                      </Button>
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
                <Button
                  ref={overflowTriggerRef}
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  className="workspace-dock__overflow"
                  aria-label={`更多标签（${overflowTabs.length} 个）`}
                >
                  <MoreHorizontal size={16} aria-hidden="true" />
                </Button>
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
        </TabsList>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              className="workspace-dock__fullscreen"
              onClick={() => setFullscreen((value) => !value)}
              aria-label={fullscreen ? "退出工作区全屏" : "工作区全屏"}
            >
              {fullscreen ? <Minimize2 size={16} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{fullscreen ? "退出全屏" : "全屏"}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              ref={collapseButtonRef}
              type="button"
              size="icon-sm"
              variant="ghost"
              className="workspace-dock__collapse"
              onClick={() => {
                setFullscreen(false);
                setDockOpen(false);
              }}
              aria-label="收起工作区"
            >
              <PanelRightClose size={16} aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>收起工作区</TooltipContent>
        </Tooltip>
      </header>
      {activeTab ? (
        <TabsContent className="workspace-dock__content" value={activeTab.viewKey}>
          {renderDockTab(
            activeTab,
            activeProjectId,
            activeConversationId,
            showToast,
            workbenchScopeId,
            addWorkbenchReference,
            registry,
            dlcDockViews,
          )}
        </TabsContent>
      ) : (
        <div className="workspace-dock__content">
          {renderDockTab(
            null,
            activeProjectId,
            activeConversationId,
            showToast,
            workbenchScopeId,
            addWorkbenchReference,
            registry,
            dlcDockViews,
          )}
        </div>
      )}
      </aside>
    </Tabs>
  );
}

function renderDockTab(
  tab: WorkspaceDockTab | null,
  activeProjectId: string,
  activeConversationId: string | null,
  showToast: WorkspaceDockProps["showToast"],
  workbenchScopeId: string,
  onAsk: (reference: WorkbenchReference) => void,
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
        description={`该工作区视图类型暂无渲染器：${tab.viewType}`}
      />
    );
  }
  return (
    <div className="workspace-dock__body-slot" key={tab.viewKey}>
      {contribution.render(tab, {
        activeProjectId,
        activeConversationId,
        showToast,
        workbenchScopeId,
        onAsk,
      })}
    </div>
  );
}
