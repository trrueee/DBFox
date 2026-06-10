import { ChevronDown, ChevronRight, Code2, Database, HardDrive, RefreshCw, Settings, Table2 } from "lucide-react";
import type { DataSource, SchemaTable } from "../../lib/api";

interface TableGroup {
  tag: string;
  tables: SchemaTable[];
}

interface WorkbenchSidebarProps {
  datasources: DataSource[];
  activeDataSource: DataSource | null;
  schemaTables: SchemaTable[];
  groupedTables: TableGroup[];
  loadingTree: boolean;
  loadingObjects: boolean;
  treeSearch: string;
  collapsedGroups: Set<string>;
  tablesFolderExpanded: boolean;
  activeTableName?: string;
  onSelectDataSource: (datasource: DataSource) => void;
  onRefreshSchema: (datasourceId: string) => void;
  onOpenTable: (tableName: string, subTab?: "data" | "schema" | "er" | "design") => void;
  onOpenSemanticSettings: () => void;
  onTreeSearchChange: (value: string) => void;
  onToggleTablesFolder: () => void;
  onToggleGroup: (tag: string) => void;
  onTableContextMenu: (tableName: string, x: number, y: number) => void;
  onDragTableSql: (event: React.DragEvent, tableName: string) => void;
}

export function WorkbenchSidebar({
  datasources,
  activeDataSource,
  schemaTables,
  groupedTables,
  loadingTree,
  loadingObjects,
  treeSearch,
  collapsedGroups,
  tablesFolderExpanded,
  activeTableName,
  onSelectDataSource,
  onRefreshSchema,
  onOpenTable,
  onOpenSemanticSettings,
  onTreeSearchChange,
  onToggleTablesFolder,
  onToggleGroup,
  onTableContextMenu,
  onDragTableSql,
}: WorkbenchSidebarProps) {
  return (
    <div className="h-full flex flex-col">
      <header className="wb-sidebar-header">
        <span className="inline-flex items-center gap-1.5">
          <Code2 size={12} />
          对象资源管理器
        </span>
        {activeDataSource && (
          <button className="wb-icon-button" title="刷新结构" onClick={() => onRefreshSchema(activeDataSource.id)} disabled={loadingObjects}>
            <RefreshCw size={12} className={loadingObjects ? "animate-spin" : ""} />
          </button>
        )}
      </header>

      <div className="wb-sidebar-body">
        {loadingTree ? (
          <div className="flex flex-col gap-2 p-2">
            <div className="h-6 rounded-md bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />
            <div className="h-6 rounded-md bg-gradient-to-r from-secondary via-muted to-secondary bg-[length:200%_100%] animate-shimmer" />
          </div>
        ) : datasources.length === 0 ? (
          <div className="wb-sidebar-empty">还没有数据源。请先打开连接管理器创建连接。</div>
        ) : (
          <div className="wb-tree-section">
            {datasources.map((datasource) => {
              const connected = activeDataSource?.id === datasource.id;
              return (
                <section key={datasource.id} className="wb-tree-section">
                  <button className={`wb-tree-row ${connected ? "wb-tree-row--active" : ""}`} onClick={() => onSelectDataSource(datasource)}>
                    {connected ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                    <Database size={13} />
                    <span className="wb-tree-label">{datasource.name}</span>
                    <span className="wb-tree-meta">{datasource.env || "dev"}</span>
                  </button>

                  {connected && (
                    <div className="wb-tree-section">
                      <div className="wb-tree-row">
                        <HardDrive size={13} />
                        <span className="wb-tree-label">{datasource.database_name}</span>
                        <span className="wb-tree-meta">{datasource.db_type || "mysql"}</span>
                      </div>

                      <button className="wb-tree-row" onClick={onOpenSemanticSettings}>
                        <Settings size={13} />
                        <span className="wb-tree-label">Semantic Settings</span>
                      </button>

                      <button className="wb-tree-row" onClick={onToggleTablesFolder}>
                        {tablesFolderExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        <Table2 size={13} />
                        <span className="wb-tree-label">表</span>
                        <span className="wb-tree-meta">{schemaTables.length}</span>
                      </button>

                      {tablesFolderExpanded && (
                        <div>
                          <div className="wb-tree-search">
                            <input placeholder="过滤数据表..." value={treeSearch} onChange={(event) => onTreeSearchChange(event.target.value)} />
                            <button title="刷新表结构" onClick={() => onRefreshSchema(datasource.id)} disabled={loadingObjects}>
                              <RefreshCw size={12} className={loadingObjects ? "animate-spin" : ""} />
                            </button>
                          </div>

                          {groupedTables.map(({ tag, tables }) => {
                            const collapsed = collapsedGroups.has(tag);
                            return (
                              <div className="wb-tree-group" key={tag}>
                                <button className="wb-tree-group-title" onClick={() => onToggleGroup(tag)}>
                                  {collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
                                  <span className="wb-tree-label">{tag}</span>
                                  <span className="wb-tree-meta">{tables.length}</span>
                                </button>

                                {!collapsed && tables.map((table) => {
                                  const active = activeTableName === table.table_name;
                                  return (
                                    <button
                                      key={table.id}
                                      draggable
                                      className={`wb-tree-row wb-tree-table ${active ? "wb-tree-row--active" : ""}`}
                                      title={`${table.table_name}${table.table_comment ? ` · ${table.table_comment}` : ""}`}
                                      onClick={() => onOpenTable(table.table_name, "schema")}
                                      onDoubleClick={() => onOpenTable(table.table_name, "data")}
                                      onDragStart={(event) => onDragTableSql(event, table.table_name)}
                                      onContextMenu={(event) => {
                                        event.preventDefault();
                                        onTableContextMenu(table.table_name, event.clientX, event.clientY);
                                      }}
                                    >
                                      <Table2 size={13} />
                                      <span className="wb-tree-label">{table.table_name}</span>
                                    </button>
                                  );
                                })}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
