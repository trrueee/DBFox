import type { MouseEvent } from "react";
import { Bot, FileText, GitMerge, Info, MessageSquare, Plus, Sparkles, Terminal, TrendingUp, X } from "lucide-react";
import type { WorkspaceTab } from "../../mock/databoxMock";

interface WorkspaceTabsProps {
  tabs: WorkspaceTab[];
  activeTabId: string;
  rightDrawerOpen: boolean;
  rightDrawerType: "ai-suggest" | "props";
  onActivateTab: (tab: WorkspaceTab) => void;
  onCloseTab: (tabId: string, event: MouseEvent) => void;
  onOpenSqlConsole: () => void;
  onOpenLlmSettings: () => void;
  onToggleRightDrawer: (type: "ai-suggest" | "props") => void;
}

export function WorkspaceTabs({
  tabs,
  activeTabId,
  rightDrawerOpen,
  rightDrawerType,
  onActivateTab,
  onCloseTab,
  onOpenSqlConsole,
  onOpenLlmSettings,
  onToggleRightDrawer,
}: WorkspaceTabsProps) {
  return (
    <div className="hifi-workspace-tab-bar">
      <div className="hifi-workspace-tabs-scroll">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <div key={tab.id} className={`hifi-workspace-tab ${isActive ? "active" : ""}`} onClick={() => onActivateTab(tab)}>
              {tab.type === "smart-query" && <Sparkles size={11} className="text-purple-500" />}
              {tab.type === "table" && <FileText size={11} className="text-blue-500" />}
              {tab.type === "sql" && <Terminal size={11} className="text-green-500" />}
              {tab.type === "multi-table" && <GitMerge size={11} className="text-orange-500" />}
              {tab.type === "query-result" && <TrendingUp size={11} className="text-purple-500" />}
              {tab.type === "conversation-history" && <MessageSquare size={11} className="text-indigo-500" />}
              {tab.type === "llm-settings" && <Bot size={11} className="text-purple-600" />}
              <span className="truncate max-w-[100px]">{tab.title}</span>
              <X size={10} className="hifi-tab-close ml-1.5 opacity-60 hover:opacity-100" onClick={(event) => onCloseTab(tab.id, event)} />
            </div>
          );
        })}
        <button className="hifi-tab-add-btn" onClick={onOpenSqlConsole} title="新建 SQL 查询">
          <Plus size={11} />
        </button>
      </div>

      <div className="hifi-workspace-tab-actions">
        <button className="hifi-right-drawer-toggle-btn" onClick={onOpenLlmSettings}>
          <Bot size={11} />
          <span>模型配置</span>
        </button>
        <button
          className={`hifi-right-drawer-toggle-btn ${rightDrawerOpen && rightDrawerType === "ai-suggest" ? "active" : ""}`}
          onClick={() => onToggleRightDrawer("ai-suggest")}
        >
          <Sparkles size={11} />
          <span>AI 建议</span>
        </button>
        <button
          className={`hifi-right-drawer-toggle-btn ${rightDrawerOpen && rightDrawerType === "props" ? "active" : ""}`}
          onClick={() => onToggleRightDrawer("props")}
        >
          <Info size={11} />
          <span>属性</span>
        </button>
      </div>
    </div>
  );
}
