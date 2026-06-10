import type { MouseEvent } from "react";
import { ChevronDown, ChevronRight, Database, FileText, RefreshCw, Search } from "lucide-react";
import { treeModules } from "../../mock/databoxMock";

interface DataSourceTreeProps {
  treeSearch: string;
  selectedTables: string[];
  onTreeSearchChange: (value: string) => void;
  onTableClick: (tableName: string, event: MouseEvent) => void;
  onTableDoubleClick: (tableName: string) => void;
  onNodeContextMenu: (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => void;
  onRefresh: () => void;
}

export function DataSourceTree({
  treeSearch,
  selectedTables,
  onTreeSearchChange,
  onTableClick,
  onTableDoubleClick,
  onNodeContextMenu,
  onRefresh,
}: DataSourceTreeProps) {
  const filteredTreeModules = treeModules
    .map((mod) => {
      const filteredTables = mod.tables.filter(
        (table) =>
          table.name.toLowerCase().includes(treeSearch.toLowerCase()) ||
          table.comment.toLowerCase().includes(treeSearch.toLowerCase()),
      );
      return { ...mod, tables: filteredTables };
    })
    .filter((mod) => mod.tables.length > 0);

  return (
    <section className="hifi-col hifi-sidebar-col">
      <div className="hifi-sidebar-panel">
        <div className="hifi-sidebar-header">
          <span className="hifi-sidebar-title">数据源</span>
          <RefreshCw size={12} className="text-gray-400 cursor-pointer" onClick={onRefresh} />
        </div>

        <div className="hifi-db-select" onContextMenu={(event) => onNodeContextMenu(event, "database", "prod-mysql")}>
          <Database size={16} className="text-blue-600" />
          <div className="hifi-db-info">
            <span className="hifi-db-name">prod-mysql</span>
            <span className="hifi-db-version">MySQL 8.0</span>
          </div>
          <ChevronDown size={14} className="text-gray-400" />
        </div>

        <div className="hifi-search-box">
          <Search size={12} className="hifi-search-icon" />
          <input
            type="text"
            className="hifi-search-input"
            placeholder="搜索表或字段"
            value={treeSearch}
            onChange={(event) => onTreeSearchChange(event.target.value)}
          />
        </div>

        <div className="hifi-tree-container">
          <div className="hifi-tree-node opacity-60">
            <ChevronRight size={12} className="mr-1 text-gray-400" />
            <Database size={12} className="mr-1 text-gray-500" />
            <span>information_schema</span>
          </div>
          <div className="hifi-tree-node opacity-60">
            <ChevronRight size={12} className="mr-1 text-gray-400" />
            <Database size={12} className="mr-1 text-gray-500" />
            <span>lindorm</span>
          </div>

          <div
            className="hifi-tree-node font-semibold text-gray-900 cursor-pointer"
            onContextMenu={(event) => onNodeContextMenu(event, "schema", "小红书数据")}
          >
            <ChevronDown size={12} className="mr-1 text-slate-500" />
            <Database size={12} className="mr-1 text-blue-600" />
            <span>小红书数据</span>
          </div>

          {filteredTreeModules.map((mod, modIdx) => (
            <div key={`${mod.name}-${modIdx}`} style={{ marginLeft: "12px" }}>
              <div className="hifi-tree-node">
                <ChevronDown size={10} className="mr-1 text-gray-400" />
                <span className="text-gray-500 font-medium">{mod.name}</span>
              </div>

              {mod.tables.map((table) => {
                const isSelected = selectedTables.includes(table.name);
                return (
                  <div
                    key={table.name}
                    className={`hifi-tree-node ${isSelected ? "active" : ""}`}
                    style={{ marginLeft: "12px", cursor: "grab" }}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData("text/plain", table.name);
                      event.dataTransfer.effectAllowed = "copy";
                    }}
                    onClick={(event) => onTableClick(table.name, event)}
                    onDoubleClick={() => onTableDoubleClick(table.name)}
                    onContextMenu={(event) => onNodeContextMenu(event, "table", table.name)}
                  >
                    <span className="hifi-tree-indent" />
                    <FileText size={11} className="mr-1.5 opacity-70" />
                    <span className="truncate" title={table.comment}>{table.name}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
