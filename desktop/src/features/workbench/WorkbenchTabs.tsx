import { Plus, Table2, Terminal, X } from "lucide-react";
import type { WorkbenchTab } from "./types";

interface WorkbenchTabsProps {
  tabs: WorkbenchTab[];
  activeTabId: string | null;
  onSelect: (tabId: string) => void;
  onClose: (tabId: string) => void;
  onNewQuery: () => void;
  onCloseOtherTabs: () => void;
  onCloseTabsToRight: () => void;
}

function getTabIcon(tab: WorkbenchTab) {
  if (tab.resultState === "running") {
    return <span className="tab-strip__spinner">↻</span>;
  }
  return tab.type === "query" ? <Terminal size={13} /> : <Table2 size={13} />;
}

export function WorkbenchTabs({ tabs, activeTabId, onSelect, onClose, onNewQuery, onCloseOtherTabs, onCloseTabsToRight }: WorkbenchTabsProps) {
  return (
    <div className="tab-strip">
      <div className="tab-strip__list">
        {tabs.map((tab) => {
          const active = tab.id === activeTabId;
          return (
            <button key={tab.id} className={active ? "tab-strip__tab is-active" : "tab-strip__tab"} onClick={() => onSelect(tab.id)}>
              {getTabIcon(tab)}
              <span className="tab-strip__title">{tab.title}</span>
              {tab.dirty && <span className="tab-strip__dirty">●</span>}
              <span
                className="tab-strip__close"
                role="button"
                tabIndex={0}
                onClick={(event) => {
                  event.stopPropagation();
                  onClose(tab.id);
                }}
              >
                <X size={12} />
              </span>
            </button>
          );
        })}
        <button className="tab-strip__new" onClick={onNewQuery} title="新建 SQL 查询">
          <Plus size={14} />
        </button>
      </div>

      {tabs.length > 1 && (
        <div className="tab-strip__actions">
          <button onClick={onCloseOtherTabs}>关闭其他</button>
          <button onClick={onCloseTabsToRight}>关闭右侧</button>
        </div>
      )}
    </div>
  );
}
