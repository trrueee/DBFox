import type { MouseEvent } from "react";
import { FileText, GitMerge, MessageSquare, Plus, Terminal, TrendingUp, X, Cpu, Database } from "lucide-react";
import { FoxIcon } from "../../components/brand/FoxIcon";
import type { WorkspaceTab } from "../../mock/databoxMock";

interface WorkspaceTabsProps {
  tabs: WorkspaceTab[];
  activeTabId: string;
  onActivateTab: (tab: WorkspaceTab) => void;
  onCloseTab: (tabId: string, event: MouseEvent) => void;
  onOpenSqlConsole: () => void;
}

export function WorkspaceTabs({
  tabs,
  activeTabId,
  onActivateTab,
  onCloseTab,
  onOpenSqlConsole,
}: WorkspaceTabsProps) {
  return (
    <div className="hifi-workspace-tab-bar" style={{ flex: 1, minWidth: 0, borderBottom: "none" }}>
      <div className="hifi-workspace-tabs-scroll">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <div key={tab.id} className={`hifi-workspace-tab ${isActive ? "active" : ""}`} onClick={() => onActivateTab(tab)}>
              {tab.type === "smart-query" && <FoxIcon variant="app" size={13} alt="" aria-hidden="true" />}
              {tab.type === "table" && <FileText size={11} className="text-blue-500" />}
              {tab.type === "sql" && <Terminal size={11} className="text-green-500" />}
              {tab.type === "multi-table" && <GitMerge size={11} className="text-orange-500" />}
              {tab.type === "query-result" && <TrendingUp size={11} className="text-purple-500" />}
              {tab.type === "conversation-history" && <MessageSquare size={11} className="text-indigo-500" />}
              {tab.type === "llm-config" && <Cpu size={11} className="text-pink-500" />}
              {tab.type === "datasource-settings" && <Database size={11} className="text-blue-500" />}
              <span className="truncate max-w-[100px]">{tab.title}</span>
              <X size={10} className="hifi-tab-close ml-1.5 opacity-60 hover:opacity-100" onClick={(event) => onCloseTab(tab.id, event)} />
            </div>
          );
        })}
        <button className="hifi-tab-add-btn" onClick={onOpenSqlConsole} title="新建 SQL 查询">
          <Plus size={11} />
        </button>
      </div>
    </div>
  );
}
