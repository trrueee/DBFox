import type { MouseEvent } from "react";
import { Plus, Table2, Terminal, X } from "lucide-react";
import type { WorkbenchTab } from "./types";

interface WorkbenchTabsProps {
  tabs: WorkbenchTab[];
  activeTabId: string | null;
  onSelectTab: (tabId: string) => void;
  onCloseTab: (tabId: string, event?: MouseEvent) => void;
  onNewQuery: () => void;
  onCloseOtherTabs: () => void;
  onCloseTabsToRight: () => void;
}

export function WorkbenchTabs({
  tabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
  onNewQuery,
  onCloseOtherTabs,
  onCloseTabsToRight,
}: WorkbenchTabsProps) {
  return (
    <div className="wb-tab-strip">
      <div className="wb-tabs-scroll">
        {tabs.map((tab) => {
          const active = tab.id === activeTabId;
          return (
            <div
              key={tab.id}
              className={`wb-tab ${active ? "wb-tab--active" : ""}`}
              onClick={() => onSelectTab(tab.id)}
              onContextMenu={(event) => {
                event.preventDefault();
                onCloseTab(tab.id);
              }}
              title={tab.title}
            >
              {tab.resultState === "running" ? (
                <span className="animate-spin text-[0.68rem]">↻</span>
              ) : tab.type === "query" ? (
                <Terminal size={12} />
              ) : (
                <Table2 size={12} />
              )}
              <span className="wb-tab-title">{tab.title}</span>
              {tab.dirty && <span className="text-[var(--accent-amber)] text-[0.64rem]">●</span>}
              <button
                className="wb-tab-close"
                type="button"
                onClick={(event) => onCloseTab(tab.id, event)}
                title="关闭"
              >
                <X size={11} />
              </button>
            </div>
          );
        })}

        <button className="wb-icon-button mb-[5px]" type="button" onClick={onNewQuery} title="新建 SQL 查询 Ctrl+T">
          <Plus size={13} />
        </button>
      </div>

      {tabs.length > 1 && (
        <div className="wb-tab-actions">
          <button className="wb-text-button" type="button" onClick={onCloseOtherTabs}>关闭其他</button>
          <button className="wb-text-button" type="button" onClick={onCloseTabsToRight}>关闭右侧</button>
        </div>
      )}
    </div>
  );
}
