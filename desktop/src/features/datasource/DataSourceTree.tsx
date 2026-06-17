import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Check, ChevronDown, Database, FileText, Plus, RefreshCw, Search } from "lucide-react";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";

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

  if (collapsed) {
    return (
      <section className="hifi-col hifi-sidebar-col" style={{ width: 36, flexShrink: 0, background: "var(--sidebar-bg)", borderRight: "1px solid var(--hairline)", display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 8 }}>
        <button
          onClick={onToggleCollapse}
          title="展开侧栏"
          style={{ border: "none", background: "transparent", color: "var(--color-text-secondary)", cursor: "pointer", padding: 4, display: "flex" }}
        >
          <ChevronDown size={14} style={{ transform: "rotate(-90deg)" }} />
        </button>
      </section>
    );
  }

  return (
    <section className="hifi-col hifi-sidebar-col" style={{ width: sidebarWidth, flexShrink: 0, minWidth: 180, maxWidth: 480, background: "var(--sidebar-bg)" }}>
      <div className="hifi-sidebar-panel">
        <div className="hifi-sidebar-header" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span className="hifi-sidebar-title" style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-text-primary)" }}>数据源</span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              onClick={onNewConnection}
              title="新建连接"
              style={{ border: "none", background: "transparent", color: "var(--color-text-secondary)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", padding: 2 }}
            >
              <Plus size={15} strokeWidth={1.5} />
            </button>
            <span title="刷新" onClick={handleRefresh} className="cursor-pointer" style={{ display: "flex", alignItems: "center" }}>
              <RefreshCw size={13} className={`text-gray-400 ${loading ? "animate-spin" : ""}`} />
            </span>
            <button
              onClick={onToggleCollapse}
              title="收起侧栏"
              style={{ border: "none", background: "transparent", color: "var(--color-text-secondary)", cursor: "pointer", padding: 2, display: "flex", alignItems: "center" }}
            >
              <ChevronDown size={14} style={{ transform: "rotate(90deg)" }} />
            </button>
          </div>
        </div>

        {activeDatasource ? (
          <div ref={dbDropdownRef} style={{ position: "relative" }}>
            <div
              className="hifi-db-select"
              onClick={() => setDbDropdownOpen((v) => !v)}
              onContextMenu={(event) => onNodeContextMenu(event, "database", activeDatasource.name)}
              style={{ cursor: "pointer" }}
            >
              <Database size={16} className="text-blue-600" />
              <div className="hifi-db-info">
                <span className="hifi-db-name">{activeDatasource.name}</span>
                <span className="hifi-db-version">{activeDatasource.db_type} · {activeDatasource.status || "unknown"}</span>
              </div>
              <ChevronDown size={14} className="text-gray-400" style={{ transform: dbDropdownOpen ? "rotate(180deg)" : undefined, transition: "transform 0.15s" }} />
            </div>
            {dbDropdownOpen && datasources.length > 0 && (
              <div
                style={{
                  position: "absolute", top: "100%", left: 4, right: 4, zIndex: 50,
                  background: "var(--bg-surface, #fff)", border: "1px solid var(--border-medium, #e5e7eb)",
                  borderRadius: 8, boxShadow: "0 4px 12px rgba(0,0,0,0.1)", marginTop: 4, overflow: "hidden",
                }}
              >
                {datasources.map((ds) => (
                  <div
                    key={ds.id}
                    onClick={() => { setActiveDatasourceId(ds.id); setDbDropdownOpen(false); }}
                    style={{
                      display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                      cursor: "pointer", fontSize: 12,
                      background: ds.id === activeDatasourceId ? "var(--color-accent, #f0f4ff)" : "transparent",
                      color: ds.id === activeDatasourceId ? "var(--color-primary, #1e3a5f)" : "var(--color-text-primary, #111827)",
                    }}
                  >
                    <Database size={12} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 500 }}>{ds.name}</div>
                      <div style={{ fontSize: 10, color: "var(--color-text-secondary, #6b7280)" }}>{ds.db_type}</div>
                    </div>
                    {ds.id === activeDatasourceId && <Check size={14} style={{ color: "var(--color-primary, #1e3a5f)" }} />}
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
                className="mr-1 text-slate-500"
                style={{ transform: schemaCollapsed ? "rotate(-90deg)" : undefined, transition: "transform 0.15s" }}
              />
              <Database size={12} className="mr-1 text-blue-600" />
              <span>{activeDatasource.database_name || activeDatasource.name}</span>
            </div>
          )}

          {!schemaCollapsed && Object.entries(groupedTables).map(([moduleName, moduleTables]) => {
            const groupCollapsed = collapsedGroups.has(moduleName);
            return (
            <div key={moduleName} style={{ marginLeft: "12px" }}>
              <div
                className="hifi-tree-node"
                style={{ cursor: "pointer" }}
                onClick={() => toggleGroup(moduleName)}
              >
                <ChevronDown
                  size={10}
                  className="mr-1 text-gray-400"
                  style={{ transform: groupCollapsed ? "rotate(-90deg)" : undefined, transition: "transform 0.15s" }}
                />
                <span className="text-gray-500 font-medium">{moduleName}</span>
              </div>

              {!groupCollapsed && moduleTables.map((table) => {
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
