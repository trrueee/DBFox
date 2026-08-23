import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import { Check, ChevronDown, Database, FileText, Plus, Search } from "lucide-react";
import { useDatasourceState } from "../datasource/useDatasourceState";
import { useTableWorkspaceStore } from "../../stores/tableWorkspaceStore";
import { useSqlConsoleStore } from "../../stores/sqlConsoleStore";
import { DatabaseBrandIcon } from "../datasource/DatabaseBrandIcon";
import { isDatabaseBrandType } from "../datasource/databaseBrandData";
import type { ContextMenuState } from "../../types/workspace";
import type { ResourceConnectorContribution } from "./types";
import { useConnectionDialogStore } from "./connectionDialogStore";
import { useConversationStore } from "../../stores/conversationStore";
import {
  EMPTY_CONVERSATION_CONTEXT,
  useConversationContextStore,
} from "../../stores/conversationContextStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import {
  addCurrentConversationContextResource,
  removeCurrentConversationContextResource,
} from "../conversation/conversationContextSelection";

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
  const [tableFilterState, setTableFilterState] = useState({ datasourceId: "", value: "" });

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
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const mainSurface = useWorkspaceStore((s) => s.mainSurfaceByProject[projectId]);
  const activeConversation = useConversationStore((s) => (
    activeConversationId ? s.detailById[activeConversationId] : undefined
  ));
  const draftResourceIntents = useConversationContextStore(
    (s) => s.byProject[projectId] ?? EMPTY_CONVERSATION_CONTEXT,
  );
  const selectedResourceIntents = mainSurface?.kind === "conversation" && activeConversation?.project_id === projectId
    ? activeConversation.resource_intents
    : draftResourceIntents;

  const visibleTables = useMemo(
    () => (typeof tables === "object" && Array.isArray(tables) ? tables : []),
    [tables],
  );
  const tableFilter = tableFilterState.datasourceId === activeDatasourceId
    ? tableFilterState.value
    : "";
  const normalizedFilter = tableFilter.trim().toLocaleLowerCase();
  const filteredTables = useMemo(() => {
    if (!normalizedFilter) return visibleTables;
    return visibleTables.filter((table) => (
      table.table_name.toLocaleLowerCase().includes(normalizedFilter)
      || (table.table_comment ?? "").toLocaleLowerCase().includes(normalizedFilter)
    ));
  }, [normalizedFilter, visibleTables]);

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
      <div className="ds-connector-tree">
        {!loading && !activeDatasource && datasources.length === 0 && (
          <div className="ds-tree-status">还没有连接。点击 + 新建数据库连接。</div>
        )}
        {datasources.map((datasource) => {
          const isActive = datasource.id === activeDatasourceId;
          const isInConversationContext = selectedResourceIntents.some(
            (ref) => ref.kind === "dbfox.data.database" && ref.id === datasource.id,
          );
          return (
            <div key={datasource.id} className="ds-tree-item-group">
              <div className="ds-tree-datasource-entry">
                <button
                  type="button"
                  className={`hifi-tree-node ds-tree-datasource-row ${isActive ? "is-expanded" : ""}`}
                  onClick={() => setActiveDatasourceId(isActive ? "" : datasource.id)}
                  onContextMenu={(event) => handleNodeContextMenu(event, "database", datasource.name)}
                  aria-expanded={isActive}
                  aria-current={isActive ? "page" : undefined}
                >
                  <ChevronDown
                    size={12}
                    className={`ds-group-chevron ${isActive ? "" : "ds-group-chevron-collapsed"}`}
                  />
                  {isDatabaseBrandType(datasource.db_type) ? (
                    <DatabaseBrandIcon dbType={datasource.db_type} size={14} className="ds-datasource-icon" />
                  ) : (
                    <Database size={14} className="ds-datasource-icon" />
                  )}
                  <span className="ds-tree-table-name">{datasource.name}</span>
                </button>
                <button
                  type="button"
                  className={`ds-tree-context-toggle ${isInConversationContext ? "is-selected" : ""}`}
                  aria-label={`${isInConversationContext ? "移出" : "加入"}对话上下文：${datasource.name}`}
                  title={isInConversationContext ? "移出对话上下文" : "加入对话上下文"}
                  onClick={() => {
                    const ref = { kind: "dbfox.data.database", id: datasource.id };
                    const action = isInConversationContext
                      ? removeCurrentConversationContextResource(ref)
                      : addCurrentConversationContextResource(ref);
                    void action
                      .then(() => toast(isInConversationContext ? "已移出对话上下文" : "已加入对话上下文"))
                      .catch(() => toast("对话上下文更新失败"));
                  }}
                >
                  {isInConversationContext
                    ? <Check size={13} aria-hidden="true" />
                    : <Plus size={13} aria-hidden="true" />}
                </button>
              </div>

              {isActive ? (
                <div className="ds-tree-item-children">
                  {error && <div className="ds-tree-status ds-tree-status--error" role="alert">{error}</div>}
                  {loading && <div className="ds-tree-status" role="status">正在加载数据库…</div>}
                  {!loading && !error && visibleTables.length === 0 && (
                    <div className="ds-tree-status">暂无表结构，请先同步数据源。</div>
                  )}
                  {!loading && !error && visibleTables.length > 0 && (
                    <>
                      {visibleTables.length > 8 ? (
                        <label className="ds-tree-filter">
                          <Search size={12} aria-hidden="true" />
                          <input
                            type="search"
                            value={tableFilter}
                            onChange={(event) => setTableFilterState({
                              datasourceId: activeDatasourceId,
                              value: event.target.value,
                            })}
                            placeholder="筛选表"
                            aria-label={`筛选 ${datasource.name} 中的表`}
                          />
                          <span className="ds-tree-filter-count" aria-hidden="true">
                            {normalizedFilter ? `${filteredTables.length}/${visibleTables.length}` : visibleTables.length}
                          </span>
                        </label>
                      ) : null}
                      {normalizedFilter && filteredTables.length === 0 ? (
                        <div className="ds-tree-status">没有匹配的表。</div>
                      ) : null}
                      {filteredTables.map((table) => {
                        const isSelected = selectedTables.includes(table.table_name);
                        return (
                          <button
                            type="button"
                            key={table.id}
                            className={`hifi-tree-node ds-tree-table-row ds-tree-table-row--depth-1 ${isSelected ? "active" : ""}`}
                            onClick={(event) => handleTableClick(table.table_name, event)}
                            onDoubleClick={() => openDockTableForActiveDatasource(table.table_name)}
                            onContextMenu={(event) => handleNodeContextMenu(event, "table", table.table_name)}
                            aria-pressed={isSelected}
                          >
                            <FileText size={13} className="ds-tree-table-icon" />
                            <span className="ds-tree-table-name" title={table.table_comment}>{table.table_name}</span>
                          </button>
                        );
                      })}
                    </>
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
            onOpenMultiTableWorkspace={(tables) => {
              openDockMultiTable(
                tables,
                activeDatasource ? { id: activeDatasource.id, dbType: activeDatasource.db_type ?? null } : undefined,
              );
            }}
            onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
            onToast={toast}
            onOpenProps={() => {}}
          />
        </Suspense>
      )}
    </>
  );
}
