import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Database, HardDrive, RefreshCw, Search, Settings, Table2 } from "lucide-react";
import type { DataSource, SchemaTable } from "../../lib/api";
import { groupSchemaTables } from "./moduleGroups";
import type { TableSubTab } from "./types";

interface ObjectExplorerProps {
  datasources: DataSource[];
  activeDataSource: DataSource | null;
  schemaTables: SchemaTable[];
  loadingTree: boolean;
  loadingObjects: boolean;
  onSelectDataSource: (datasource: DataSource) => void;
  onOpenTable: (tableName: string, tab: TableSubTab) => void;
  onRefreshTables: (datasourceId: string) => void;
  onOpenDataSources: () => void;
  onOpenSemanticSettings: () => void;
}

export function ObjectExplorer({
  datasources,
  activeDataSource,
  schemaTables,
  loadingTree,
  loadingObjects,
  onSelectDataSource,
  onOpenTable,
  onRefreshTables,
  onOpenDataSources,
  onOpenSemanticSettings,
}: ObjectExplorerProps) {
  const [search, setSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const groups = useMemo(() => groupSchemaTables(schemaTables, search), [schemaTables, search]);

  const toggleGroup = (tag: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  return (
    <div className="object-explorer">
      <div className="object-explorer__header">
        <div>
          <div className="object-explorer__eyebrow">Workspace</div>
          <div className="object-explorer__title">对象资源管理器</div>
        </div>
        <button className="icon-button" onClick={onOpenDataSources} title="连接管理">
          <Settings size={14} />
        </button>
      </div>

      <div className="object-explorer__scroll">
        {loadingTree ? (
          <div className="object-explorer__empty">正在加载连接...</div>
        ) : datasources.length === 0 ? (
          <div className="object-explorer__empty">
            <Database size={22} />
            <span>还没有数据源</span>
            <button className="text-button" onClick={onOpenDataSources}>新建连接</button>
          </div>
        ) : (
          <div className="object-explorer__section">
            <div className="object-explorer__section-title">Connections</div>
            {datasources.map((datasource) => {
              const active = activeDataSource?.id === datasource.id;
              return (
                <div key={datasource.id} className="object-explorer__connection">
                  <button
                    className={active ? "tree-row tree-row--active" : "tree-row"}
                    onClick={() => onSelectDataSource(datasource)}
                  >
                    {active ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    <Database size={14} />
                    <span className="tree-row__label">{datasource.name}</span>
                    {datasource.env && <span className={`env-pill env-pill--${datasource.env}`}>{datasource.env}</span>}
                  </button>

                  {active && (
                    <div className="object-explorer__database">
                      <div className="tree-row tree-row--muted">
                        <HardDrive size={13} />
                        <span className="tree-row__label">{datasource.database_name}</span>
                      </div>

                      <button className="tree-row" onClick={onOpenSemanticSettings}>
                        <Settings size={13} />
                        <span className="tree-row__label">Semantic Settings</span>
                      </button>

                      <div className="object-explorer__filter">
                        <Search size={12} />
                        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="过滤表名或备注" />
                        <button onClick={() => onRefreshTables(datasource.id)} disabled={loadingObjects} title="刷新结构">
                          <RefreshCw size={12} className={loadingObjects ? "animate-spin" : undefined} />
                        </button>
                      </div>

                      <div className="object-explorer__section-title">Tables · {schemaTables.length}</div>
                      {groups.length === 0 ? (
                        <div className="object-explorer__empty object-explorer__empty--small">没有匹配的数据表</div>
                      ) : groups.map((group) => {
                        const collapsed = collapsedGroups.has(group.tag);
                        return (
                          <div key={group.tag} className="table-group">
                            <button className="table-group__header" onClick={() => toggleGroup(group.tag)}>
                              {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                              <span>{group.tag}</span>
                              <b>{group.tables.length}</b>
                            </button>
                            {!collapsed && group.tables.map((table) => (
                              <button
                                key={table.id}
                                className="table-row"
                                title={`${table.table_name}${table.table_comment ? ` · ${table.table_comment}` : ""}`}
                                onClick={() => onOpenTable(table.table_name, "schema")}
                                onDoubleClick={() => onOpenTable(table.table_name, "data")}
                              >
                                <Table2 size={13} />
                                <span>{table.table_name}</span>
                              </button>
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
