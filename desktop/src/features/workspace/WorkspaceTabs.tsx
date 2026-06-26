import { FileText, GitMerge, MessageSquare, Plus, Terminal, TrendingUp, X, Cpu, Database, Bug } from "lucide-react";
import { FoxIcon } from "../../components/brand/FoxIcon";
import { Button, Tabs, TabsList, TabsTrigger, Tooltip, TooltipContent, TooltipTrigger } from "../../components/ui";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import type { WorkspaceTab } from "../../types/workspace";
import "./WorkspaceTabs.css";

interface WorkspaceTabsProps {
  onOpenSqlConsole: (initialSql?: string) => void;
}

function tabIcon(tab: WorkspaceTab) {
  switch (tab.type) {
    case "smart-query":
      return <FoxIcon variant="app" size={13} alt="" aria-hidden="true" />;
    case "table":
      return <FileText size={11} className="workspace-tab__icon workspace-tab__icon--table" aria-hidden="true" />;
    case "sql":
      return <Terminal size={11} className="workspace-tab__icon workspace-tab__icon--sql" aria-hidden="true" />;
    case "multi-table":
      return <GitMerge size={11} className="workspace-tab__icon workspace-tab__icon--multi-table" aria-hidden="true" />;
    case "query-result":
    case "artifact-result":
      return <TrendingUp size={11} className="workspace-tab__icon workspace-tab__icon--result" aria-hidden="true" />;
    case "conversation-history":
      return <MessageSquare size={11} className="workspace-tab__icon workspace-tab__icon--conversation" aria-hidden="true" />;
    case "llm-config":
      return <Cpu size={11} className="workspace-tab__icon workspace-tab__icon--llm" aria-hidden="true" />;
    case "datasource-settings":
      return <Database size={11} className="workspace-tab__icon workspace-tab__icon--datasource" aria-hidden="true" />;
    case "diagnostics":
      return <Bug size={11} className="workspace-tab__icon workspace-tab__icon--diagnostics" aria-hidden="true" />;
    default:
      return null;
  }
}

export function WorkspaceTabs({ onOpenSqlConsole }: WorkspaceTabsProps) {
  const tabs = useWorkspaceStore((s) => s.tabs);
  const activeTabId = useWorkspaceStore((s) => s.activeTabId);
  const setActiveTabId = useWorkspaceStore((s) => s.setActiveTabId);
  const setSelectedTables = useWorkspaceStore((s) => s.setSelectedTables);
  const closeTab = useWorkspaceStore((s) => s.closeTab);
  const handleTabChange = (tabId: string) => {
    const tab = tabs.find((item) => item.id === tabId);
    setActiveTabId(tabId);
    if (tab?.type === "table" && tab.tableId) setSelectedTables([tab.tableId]);
  };

  return (
    <nav className="workspace-tabs" aria-label="工作区标签">
      <Tabs className="workspace-tabs__root" value={activeTabId} onValueChange={handleTabChange}>
        <TabsList className="workspace-tabs__scroll" aria-label="工作区标签列表">
          {tabs.map((tab) => {
            const isActive = tab.id === activeTabId;
            return (
              <div key={tab.id} className={`workspace-tab ${isActive ? "is-active" : ""}`}>
                <TabsTrigger asChild value={tab.id}>
                  <Button
                    type="button"
                    variant="ghost"
                    className="workspace-tab__main"
                    title={tab.title}
                    onClick={() => handleTabChange(tab.id)}
                  >
                    {tabIcon(tab)}
                    <span className="workspace-tab__title">{tab.title}</span>
                  </Button>
                </TabsTrigger>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="workspace-tab__close"
                      aria-label={`关闭 ${tab.title}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        closeTab(tab.id);
                      }}
                    >
                      <X size={10} aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>关闭 {tab.title}</TooltipContent>
                </Tooltip>
              </div>
            );
          })}
        </TabsList>
      </Tabs>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="workspace-tabs__add"
            onClick={() => onOpenSqlConsole()}
            aria-label="新建 SQL 查询"
          >
            <Plus size={11} aria-hidden="true" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>新建 SQL 查询</TooltipContent>
      </Tooltip>
    </nav>
  );
}
