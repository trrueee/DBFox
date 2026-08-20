import { useMemo } from "react";
import {
  HelpCircle,
  PanelRightClose,
  PanelRightOpen,
  X,
} from "lucide-react";
import { EmptyState, Tooltip, TooltipContent, TooltipTrigger } from "../../components/ui";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import type { WorkspaceDockTab } from "../../types/workspace";
import type { DockViewRegistry } from "../dock/dockViewComposition";
import { DEFAULT_REGISTRY, dockViewTitle } from "../dock/dockViewComposition";
import { useDlcStore } from "../dlc/extensionStore";
import type { DockViewContribution } from "../dock/types";
import "./WorkspaceDock.css";

export interface WorkspaceDockProps {
  activeDatasourceId?: string;
  activeConversationId: string | null;
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
  registry?: DockViewRegistry;
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
    <aside className="workspace-dock" aria-label="工作台 Dock">
      <header className="workspace-dock__tabbar">
        <div className="workspace-dock__tabs" role="tablist" aria-label="工作台标签">
          {visibleTabs.map((tab) => {
            const active = tab.viewKey === activeTab?.viewKey;
            return (
              <div
                key={tab.viewKey}
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
