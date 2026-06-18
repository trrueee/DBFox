import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Check, ChevronDown, Database, FileText, Plus, RefreshCw, Search } from "lucide-react";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import type { EngineSchemaTable } from "../engine/engineApi";
import "./DataSourceTree.css";

interface DataSourceTreeProps {
  treeSearch: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onTreeSearchChange: (value: string) => void;
  onTableClick: (tableName: string, event: MouseEvent) => void;
  onTableDoubleClick: (tableName: string) => void;
  onNodeContextMenu: (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => void;
  onRefresh: () => void;
  onNewConnection: () => void;
  sidebarWidth: number;
}

export function DataSourceTree({
  treeSearch,
  collapsed,
  onToggleCollapse,
  onTreeSearchChange,
  onTableClick,
  onTableDoubleClick,
  onNodeContextMenu,
  onRefresh,
  onNewConnection,
  sidebarWidth,
}: DataSourceTreeProps) {
  const datasources = useDatasourceStore((s) => s.datasources);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  const setActiveDatasourceId = useDatasourceStore((s) => s.setActiveDatasourceId);
  const tables = useDatasourceStore((s) => s.tables);
  const loading = useDatasourceStore((s) => s.loadingSchema);
  const error = useDatasourceStore((s) => s.schemaError);
  const selectedTables = useWorkspaceStore((s) => s.selectedTables);

  const activeDatasource = datasources.find((item) => item.id === activeDatasourceId) ?? datasources[0];
  const [dbDropdownOpen, setDbDropdownOpen] = useState(false);
  const dbDropdownRef = useRef<HTMLDivElement>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [schemaCollapsed, setSchemaCollapsed] = useState(false);

  useEffect(() => {
    if (!dbDropdownOpen) return;
    const handleClick = (e: Event) => {
      if (dbDropdownRef.current && !dbDropdownRef.current.contains(e.target as Node)) {
        setDbDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [dbDropdownOpen]);

  const toggleGroup = (groupName: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupName)) next.delete(groupName);
      else next.add(groupName);
      return next;
    });
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

  if (collapsed) {
    return (
      <section className="hifi-col hifi-sidebar-col ds-tree-collapsed">
        <button onClick={onToggleCollapse} title="展开侧栏" className="ds-tree-expand-btn">
          <ChevronDown size={14} className="ds-tree-chevron-left" />
        </button>
      </section>
    );
  }

  return (
    <section className="hifi-col hifi-sidebar-col ds-tree-main" style={{ width: sidebarWidth, "--sidebar-width": `${sidebarWidth}px` } as React.CSSProperties}>
      <div className="hifi-sidebar-panel">
        <div className="hifi-sidebar-header ds-tree-header-row">
          <span className="ds-tree-title">数据源</span>
          <div className="ds-tree-actions">
            <button onClick={onNewConnection} title="新建连接" className="ds-tree-icon-btn">
              <Plus size={15} strokeWidth={1.5} />
            </button>
            <span title="刷新" onClick={onRefresh} className="cursor-pointer" style={{ display: "flex", alignItems: "center" }}>
              <RefreshCw size={13} className={`text-gray-400 ${loading ? "animate-spin" : ""}`} />
            </span>
            <button onClick={onToggleCollapse} title="收起侧栏" className="ds-tree-icon-btn">
              <ChevronDown size={14} className="ds-tree-chevron-right" />
            </button>
          </div>
        </div>

        {activeDatasource ? (
          <div ref={dbDropdownRef} className="ds-db-select-wrapper">
            <div
              className="hifi-db-select ds-db-select-clickable"
              onClick={() => setDbDropdownOpen((v) => !v)}
              onContextMenu={(event) => onNodeContextMenu(event, "database", activeDatasource.name)}
            >
              <Database size={16} className="text-blue-600" />
              <div className="hifi-db-info">
                <span className="hifi-db-name">{activeDatasource.name}</span>
                <span className="hifi-db-version">{activeDatasource.db_type} · {activeDatasource.status || "unknown"}</span>
              </div>
              <ChevronDown size={14} className={`text-gray-400 ds-db-chevron ${dbDropdownOpen ? "ds-db-chevron-open" : ""}`} />
            </div>
            {dbDropdownOpen && datasources.length > 0 && (
              <div className="ds-db-dropdown">
                {datasources.map((ds) => (
                  <div
                    key={ds.id}
                    onClick={() => { setActiveDatasourceId(ds.id); setDbDropdownOpen(false); }}
                    className={`ds-db-dropdown-item ${ds.id === activeDatasourceId ? "active" : ""}`}
                  >
                    <Database size={12} />
                    <div className="ds-db-item-info">
                      <div className="ds-db-item-name">{ds.name}</div>
                      <div className="ds-db-item-type">{ds.db_type}</div>
                    </div>
                    {ds.id === activeDatasourceId && <Check size={14} className="ds-db-item-check" />}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="hifi-db-select opacity-70">
            <Database size={16} className="text-slate-400" />
            <div className="hifi-db-info">
              <span className="hifi-db-name">未连接数据源</span>
              <span className="hifi-db-version">DBFox</span>
            </div>
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
          {loading && <div className="text-[10px] text-slate-400 p-2">正在加载...</div>}
          {!loading && !error && !activeDatasource && <div className="text-[10px] text-slate-400 p-2">暂无数据源，请先创建连接。</div>}

          {activeDatasource && (
            <div
              className="hifi-tree-node font-semibold text-gray-900 cursor-pointer"
              onClick={() => setSchemaCollapsed((v) => !v)}
              onContextMenu={(event) => onNodeContextMenu(event, "schema", activeDatasource.database_name || activeDatasource.name)}
            >
              <ChevronDown
                size={12}
                className={`mr-1 text-slate-500 ds-group-chevron ${schemaCollapsed ? "ds-group-chevron-collapsed" : ""}`}
              />
              <Database size={12} className="mr-1 text-blue-600" />
              <span>{activeDatasource.database_name || activeDatasource.name}</span>
            </div>
          )}

          {!schemaCollapsed && Object.entries(groupedTables).map(([moduleName, moduleTables]) => {
            const groupCollapsed = collapsedGroups.has(moduleName);
            return (
            <div key={moduleName} className="ds-tree-group">
              <div className="hifi-tree-node ds-tree-group-header" onClick={() => toggleGroup(moduleName)}>
                <ChevronDown
                  size={10}
                  className={`mr-1 text-gray-400 ds-group-chevron ${groupCollapsed ? "ds-group-chevron-collapsed" : ""}`}
                />
                <span className="text-gray-500 font-medium">{moduleName}</span>
              </div>

              {!groupCollapsed && moduleTables.map((table) => {
                const isSelected = selectedTables.includes(table.table_name);
                return (
                  <div
                    key={table.id}
                    className={`hifi-tree-node ds-tree-table-row ${isSelected ? "active" : ""}`}
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
          );
          })}

          {activeDatasource && !loading && Object.keys(groupedTables).length === 0 && (
            <div className="text-[10px] text-slate-400 p-2">没有匹配的表。请先同步 Schema 或调整搜索词。</div>
          )}
        </div>
      </div>
    </section>
  );
}
