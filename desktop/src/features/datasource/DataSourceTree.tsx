import type { MouseEvent } from "react";
import { ChevronDown, ChevronRight, Database, FileText, RefreshCw, Search } from "lucide-react";
import type { EngineDataSource, EngineSchemaTable } from "../engine/engineApi";

interface DataSourceTreeProps {
  treeSearch: string;
  selectedTables: string[];
  onTreeSearchChange: (value: string) => void;
  onTableClick: (tableName: string, event: MouseEvent) => void;
  onTableDoubleClick: (tableName: string) => void;
  onNodeContextMenu: (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => void;
  onRefresh: () => void;
  onNewConnection: () => void;
  datasources: EngineDataSource[];
  activeDatasourceId: string;
  setActiveDatasourceId: (id: string) => void;
  tables: EngineSchemaTable[];
  loading: boolean;
  error: string;
}

export function DataSourceTree({
  treeSearch,
  selectedTables,
  onTreeSearchChange,
  onTableClick,
  onTableDoubleClick,
  onNodeContextMenu,
  onRefresh,
  onNewConnection,
  datasources,
  activeDatasourceId,
  setActiveDatasourceId,
  tables,
  loading,
  error,
}: DataSourceTreeProps) {
  const activeDatasource = datasources.find((item) => item.id === activeDatasourceId) ?? datasources[0];

  const handleRefresh = () => {
    onRefresh();
  };

  const groupedTables = typeof tables === "object" && Array.isArray(tables) ? tables.reduce<Record<string, EngineSchemaTable[]>>((acc, table) => {
    const keyword = treeSearch.trim().toLowerCase();
    const matches = !keyword || table.table_name.toLowerCase().includes(keyword) || (table.table_comment || "").toLowerCase().includes(keyword);
    if (matches) {
      const groupName = table.module_tag || "未分组表";
      if (!acc[groupName]) acc[groupName] = [];
      acc[groupName].push(table);
    }
    return acc;
  }, {}) : {};

  return (
    <section className="hifi-col hifi-sidebar-col">
      <div className="hifi-sidebar-panel">
        <div className="hifi-sidebar-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span className="hifi-sidebar-title" style={{ fontSize: "12px", fontWeight: 700, color: "var(--color-text-primary)" }}>数据源</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              onClick={onNewConnection}
              title="新建连接"
              style={{ border: "none", background: "transparent", color: "var(--color-text-secondary)", cursor: "pointer", fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center", padding: 2 }}
            >
              +
            </button>
            <RefreshCw size={12} className={`text-gray-400 cursor-pointer ${loading ? "animate-spin" : ""}`} onClick={handleRefresh} title="刷新" />
          </div>
        </div>

        {activeDatasource ? (
          <div className="hifi-db-select" onContextMenu={(event) => onNodeContextMenu(event, "database", activeDatasource.name)}>
            <Database size={16} className="text-blue-600" />
            <div className="hifi-db-info">
              <span className="hifi-db-name">{activeDatasource.name}</span>
              <span className="hifi-db-version">{activeDatasource.db_type} · {activeDatasource.status || "unknown"}</span>
            </div>
            <ChevronDown size={14} className="text-gray-400" />
          </div>
        ) : (
          <div className="hifi-db-select opacity-70">
            <Database size={16} className="text-slate-400" />
            <div className="hifi-db-info">
              <span className="hifi-db-name">未连接数据源</span>
              <span className="hifi-db-version">Local Engine</span>
            </div>
          </div>
        )}

        {datasources.length > 1 && (
          <div className="px-2 pb-2">
            <select className="w-full border border-slate-200 rounded-lg text-[10px] px-2 py-1 bg-white" value={activeDatasource?.id || ""} onChange={(event) => setActiveDatasourceId(event.target.value)}>
              {datasources.map((datasource) => <option key={datasource.id} value={datasource.id}>{datasource.name}</option>)}
            </select>
          </div>
        )}

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
          {error && <div className="text-[10px] text-red-500 bg-red-50 rounded-lg p-2 mb-2">{error}</div>}
          {loading && <div className="text-[10px] text-slate-400 p-2">正在读取本地 Engine...</div>}
          {!loading && !error && !activeDatasource && <div className="text-[10px] text-slate-400 p-2">暂无数据源，请先创建连接。</div>}

          {activeDatasource && (
            <div
              className="hifi-tree-node font-semibold text-gray-900 cursor-pointer"
              onContextMenu={(event) => onNodeContextMenu(event, "schema", activeDatasource.database_name || activeDatasource.name)}
            >
              <ChevronDown size={12} className="mr-1 text-slate-500" />
              <Database size={12} className="mr-1 text-blue-600" />
              <span>{activeDatasource.database_name || activeDatasource.name}</span>
            </div>
          )}

          {Object.entries(groupedTables).map(([moduleName, moduleTables]) => (
            <div key={moduleName} style={{ marginLeft: "12px" }}>
              <div className="hifi-tree-node">
                <ChevronDown size={10} className="mr-1 text-gray-400" />
                <span className="text-gray-500 font-medium">{moduleName}</span>
              </div>

              {moduleTables.map((table) => {
                const isSelected = selectedTables.includes(table.table_name);
                return (
                  <div
                    key={table.id}
                    className={`hifi-tree-node ${isSelected ? "active" : ""}`}
                    style={{ marginLeft: "12px", cursor: "grab" }}
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData("text/plain", table.table_name);
                      event.dataTransfer.effectAllowed = "copy";
                    }}
                    onClick={(event) => onTableClick(table.table_name, event)}
                    onDoubleClick={() => onTableDoubleClick(table.table_name)}
                    onContextMenu={(event) => onNodeContextMenu(event, "table", table.table_name)}
                  >
                    <span className="hifi-tree-indent" />
                    <FileText size={11} className="mr-1.5 opacity-70" />
                    <span className="truncate" title={table.table_comment}>{table.table_name}</span>
                  </div>
                );
              })}
            </div>
          ))}

          {activeDatasource && !loading && Object.keys(groupedTables).length === 0 && (
            <div className="text-[10px] text-slate-400 p-2">没有匹配的表。请先同步 Schema 或调整搜索词。</div>
          )}
        </div>
      </div>
    </section>
  );
}
