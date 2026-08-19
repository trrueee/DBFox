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
import { dockViewTitle, getDockView } from "../dock/dockViewComposition";
import "./WorkspaceDock.css";

interface WorkspaceDockProps {
  activeDatasourceId?: string;
  activeConversationId: string | null;
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}

function dockTabIcon(tab: WorkspaceDockTab) {
  return getDockView(tab.viewType)?.icon(tab) ?? <HelpCircle size={13} aria-hidden="true" />;
}

export function WorkspaceDock({
  activeDatasourceId = "",
  activeConversationId,
  showToast,
}: WorkspaceDockProps) {
  const dock = useWorkspaceStore((s) => s.dock);
  const dockTabs = useWorkspaceStore((s) => s.dockTabs);
  const setDockOpen = useWorkspaceStore((s) => s.setDockOpen);
  const setDockActiveTab = useWorkspaceStore((s) => s.setDockActiveTab);
  const closeDockTab = useWorkspaceStore((s) => s.closeDockTab);
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);

  const visibleTabs = useMemo(() => {
    return dockTabs.filter((tab) => {
      const contribution = getDockView(tab.viewType);
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
  }, [activeConversationId, activeDatasourceId, activeProjectId, dockTabs]);

  const activeKey = dock.activeViewKey ?? dock.activeTabId;
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
                aria-label={dockViewTitle(tab)}
                onClick={() => setDockActiveTab(tab.viewKey)}
              >
                {dockTabIcon(tab)}
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
                    {dockTabIcon(tab)}
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
) {
  if (!tab) {
    return (
      <EmptyState
        title="没有打开的标签"
        description="从左侧数据树打开表，或从对话里发送 SQL 到控制台。"
      />
    );
  }

  const contribution = getDockView(tab.viewType);
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
