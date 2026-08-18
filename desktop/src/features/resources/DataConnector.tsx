import { lazy, Suspense, useCallback, useEffect, useState, type MouseEvent } from "react";
import { ChevronDown, Database, FileText } from "lucide-react";
import { useDatasourceState } from "../datasource/useDatasourceState";
import { useTableWorkspaceStore } from "../../stores/tableWorkspaceStore";
import { useSqlConsoleStore } from "../../stores/sqlConsoleStore";
import { DatabaseBrandIcon } from "../datasource/DatabaseBrandIcon";
import { isDatabaseBrandType } from "../datasource/databaseBrandData";
import type { ContextMenuState } from "../../types/workspace";
import type { ResourceConnectorContribution } from "./types";
import { useConnectionDialogStore } from "./connectionDialogStore";

const DataSourceContextMenu = lazy(() =>
  import("../datasource/DataSourceContextMenu").then((module) => ({
    default: module.DataSourceContextMenu,
  })),
);

export const DATA_CONNECTOR_ID = "dbfox.data";

export function createDataContribution(
  toast: (message: string) => void,
): ResourceConnectorContribution {
  return {
    id: DATA_CONNECTOR_ID,
    title: "数据库",
    icon: <Database size={13} aria-hidden="true" />,
    render: (context) => (
      <DataConnectorContent
        projectId={context.projectId}
        toast={toast}
      />
    ),
    addLabel: "新建数据库",
    onAdd: () => useConnectionDialogStore.getState().openCreate(),
  };
}

function DataConnectorContent({
  projectId,
  toast,
}: {
  projectId: string;
  toast: (message: string) => void;
}) {
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });
  const [schemaCollapsed, setSchemaCollapsed] = useState(false);

  const {
    datasources,
    activeDatasourceId,
    activeDatasource,
    setActiveDatasourceId,
    tables,
    loadingSchema: loading,
    schemaError: error,
  } = useDatasourceState(projectId);
  const openDockTable = useTableWorkspaceStore((s) => s.openTable);
  const openDockMultiTable = useTableWorkspaceStore((s) => s.openMultiTable);
  const openDockConsole = useSqlConsoleStore((s) => s.openConsole);
  const selectedTables = useTableWorkspaceStore((s) => s.selectedTables);

  const visibleTables = typeof tables === "object" && Array.isArray(tables) ? tables : [];

  const openDockTableForActiveDatasource = useCallback(
    (tableName: string, initialSubtab?: string) => {
      openDockTable(
        tableName,
        initialSubtab,
        activeDatasource ? { id: activeDatasource.id, dbType: activeDatasource.db_type ?? null } : undefined,
      );
    },
    [activeDatasource, openDockTable],
  );

  const openDockConsoleForActiveDatasource = useCallback(
    (initialSql?: string) => {
      if (!activeDatasource) return;
      openDockConsole(activeDatasource.id, activeDatasource.db_type, initialSql);
    },
    [activeDatasource, openDockConsole],
  );

  const handleTableClick = useCallback(
    (tableName: string, event: MouseEvent) => {
      if (event.ctrlKey || event.metaKey) {
        useTableWorkspaceStore.getState().setSelectedTables((prev) => (
          prev.includes(tableName) ? prev.filter((table) => table !== tableName) : [...prev, tableName]
        ));
        return;
      }
      openDockTableForActiveDatasource(tableName);
    },
    [openDockTableForActiveDatasource],
  );

  const handleNodeContextMenu = useCallback(
    (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => {
      event.preventDefault();
      event.stopPropagation();
      const currentSelectedTables = useTableWorkspaceStore.getState().selectedTables;
      const setSelectedTables = useTableWorkspaceStore.getState().setSelectedTables;
      if (type === "table" && currentSelectedTables.length > 1 && currentSelectedTables.includes(nodeName)) {
        setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type: "multi-table", targetNode: nodeName });
        return;
      }
      if (type === "table") setSelectedTables([nodeName]);
      setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type, targetNode: nodeName });
    },
    [],
  );

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  return (
    <>
      <div className="ds-entity-list">
        {!loading && !activeDatasource && datasources.length === 0 && (
          <div className="ds-tree-status">还没有连接。点击 + 新建数据库连接。</div>
        )}
        {datasources.map((datasource) => {
          const isActive = datasource.id === activeDatasourceId;
          return (
            <div key={datasource.id} className={`ds-entity-row ${isActive ? "is-active" : ""}`}>
              <div className="ds-entity-row__main">
                <button
                  type="button"
                  className="ds-entity-row__trigger"
                  onClick={() => setActiveDatasourceId(datasource.id)}
                  aria-current={isActive ? "page" : undefined}
                >
                  {isDatabaseBrandType(datasource.db_type) ? (
                    <DatabaseBrandIcon dbType={datasource.db_type} size={14} className="ds-entity-row__icon" />
                  ) : (
                    <Database size={14} className="ds-entity-row__icon" />
                  )}
                  <span className="ds-entity-row__name">{datasource.name}</span>
                </button>
              </div>

              {isActive ? (
                <div className="ds-entity-row__content">
                  {error && <div className="ds-tree-status ds-tree-status--error" role="alert">{error}</div>}
                  {loading && <div className="ds-tree-status" role="status">正在加载数据库…</div>}
                  {!loading && !error && visibleTables.length === 0 && (
                    <div className="ds-tree-status">暂无表结构，请先同步数据源。</div>
                  )}
                  {!loading && !error && visibleTables.length > 0 && (
                    <div className="ds-tree-group">
                      <button
                        type="button"
                        className="hifi-tree-node ds-tree-group-header"
                        onClick={() => setSchemaCollapsed((value) => !value)}
                        onContextMenu={(event) => handleNodeContextMenu(event, "schema", activeDatasource?.database_name || datasource.name)}
                        aria-expanded={!schemaCollapsed}
                      >
                        <ChevronDown
                          size={12}
                          className={`ds-group-chevron ds-group-chevron-muted ${schemaCollapsed ? "ds-group-chevron-collapsed" : ""}`}
                        />
                        {isDatabaseBrandType(datasource.db_type) ? (
                          <DatabaseBrandIcon dbType={datasource.db_type} size={14} className="ds-schema-icon" />
                        ) : (
                          <Database size={14} className="ds-schema-icon" />
                        )}
                        <span className="ds-tree-group-label">{activeDatasource?.database_name || datasource.name}</span>
                      </button>

                      {!schemaCollapsed && visibleTables.map((table) => {
                        const isSelected = selectedTables.includes(table.table_name);
                        return (
                          <button
                            type="button"
                            key={table.id}
                            className={`hifi-tree-node ds-tree-table-row ${isSelected ? "active" : ""}`}
                            onClick={(event) => handleTableClick(table.table_name, event)}
                            onDoubleClick={() => openDockTableForActiveDatasource(table.table_name)}
                            onContextMenu={(event) => handleNodeContextMenu(event, "table", table.table_name)}
                            aria-pressed={isSelected}
                          >
                            <span className="hifi-tree-indent" />
                            <FileText size={13} className="ds-tree-table-icon" />
                            <span className="ds-tree-table-name" title={table.table_comment}>{table.table_name}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {contextMenu.visible && (
        <Suspense fallback={null}>
          <DataSourceContextMenu
            contextMenu={contextMenu}
            onOpenSqlConsole={openDockConsoleForActiveDatasource}
            onOpenTable={(tableName, subTab) => openDockTableForActiveDatasource(tableName, subTab)}
            onOpenMultiTableWorkspace={openDockMultiTable}
            onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
            onToast={toast}
            onOpenProps={() => {}}
          />
        </Suspense>
      )}
    </>
  );
}
