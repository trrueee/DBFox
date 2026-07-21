import { useState, type MouseEvent } from "react";
import { Check, ChevronDown, Database, FileText, MessageSquare, Plus, RefreshCw, Search, Sparkles } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  ScrollArea,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "../../components/ui";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import type { EngineSchemaTable } from "../../lib/api/schema";
import { getUserErrorMessage } from "../../lib/api/client";
import { databaseTypeLabel, datasourceStatusPresentation } from "../../lib/presentation";
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
}: DataSourceTreeProps) {
  const datasources = useDatasourceStore((s) => s.datasources);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  const setActiveDatasourceId = useDatasourceStore((s) => s.setActiveDatasourceId);
  const tables = useDatasourceStore((s) => s.tables);
  const loading = useDatasourceStore((s) => s.loadingSchema);
  const error = useDatasourceStore((s) => s.schemaError);
  const selectedTables = useWorkspaceStore((s) => s.selectedTables);
  const activeTabType = useWorkspaceStore((s) => s.tabs.find((tab) => tab.id === s.activeTabId)?.type);
  const openSmartQueryTab = useWorkspaceStore((s) => s.openSmartQueryTab);
  const openConversationHistoryTab = useWorkspaceStore((s) => s.openConversationHistoryTab);

  const activeDatasource = datasources.find((item) => item.id === activeDatasourceId) ?? datasources[0];
  const activeDatasourceStatus = datasourceStatusPresentation(activeDatasource?.status);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [schemaCollapsed, setSchemaCollapsed] = useState(false);

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
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button" onClick={onToggleCollapse} aria-label="展开侧栏" className="ds-tree-expand-btn">
              <ChevronDown size={14} className="ds-tree-chevron-left" />
            </button>
          </TooltipTrigger>
          <TooltipContent>展开侧栏</TooltipContent>
        </Tooltip>
      </section>
    );
  }

  return (
    <section className="hifi-col hifi-sidebar-col ds-tree-main">
      <div className="hifi-sidebar-panel">
        <div className="hifi-sidebar-header ds-tree-header-row">
          <span className="ds-tree-title">数据源</span>
          <div className="ds-tree-actions">
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" onClick={onNewConnection} aria-label="新建连接" className="ds-tree-icon-btn">
                  <Plus size={15} strokeWidth={1.5} />
                </button>
              </TooltipTrigger>
              <TooltipContent>新建连接</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" onClick={onRefresh} aria-label="刷新" className="ds-tree-icon-btn ds-tree-refresh-btn">
                  <RefreshCw size={13} className={`ds-tree-refresh-icon ${loading ? "is-loading" : ""}`} />
                </button>
              </TooltipTrigger>
              <TooltipContent>刷新</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" onClick={onToggleCollapse} aria-label="收起侧栏" className="ds-tree-icon-btn">
                  <ChevronDown size={14} className="ds-tree-chevron-right" />
                </button>
              </TooltipTrigger>
              <TooltipContent>收起侧栏</TooltipContent>
            </Tooltip>
          </div>
        </div>

        {activeDatasource ? (
          <div className="ds-db-select-wrapper">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="hifi-db-select ds-db-select-trigger"
                  aria-label={`选择数据源 ${activeDatasource.name}`}
                  onContextMenu={(event) => onNodeContextMenu(event, "database", activeDatasource.name)}
                >
                  <Database size={16} className="ds-db-icon" />
                  <div className="hifi-db-info">
                    <span className="hifi-db-name">{activeDatasource.name}</span>
                    <span className={`hifi-db-version ds-db-status ds-db-status--${activeDatasourceStatus.tone}`}>
                      {databaseTypeLabel(activeDatasource.db_type)} · {activeDatasourceStatus.label}
                    </span>
                  </div>
                  <ChevronDown size={14} className="ds-db-chevron" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="ds-db-dropdown" align="start" sideOffset={4}>
                {datasources.map((ds) => (
                  <DropdownMenuItem
                    key={ds.id}
                    className={`ds-db-dropdown-item ${ds.id === activeDatasourceId ? "active" : ""}`}
                    onSelect={() => setActiveDatasourceId(ds.id)}
                  >
                    <Database size={12} className="ds-db-item-icon" />
                    <div className="ds-db-item-info">
                      <div className="ds-db-item-name">{ds.name}</div>
                      <div className="ds-db-item-type">
                        {databaseTypeLabel(ds.db_type)} · {datasourceStatusPresentation(ds.status).label}
                      </div>
                    </div>
                    {ds.id === activeDatasourceId && <Check size={14} className="ds-db-item-check" />}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ) : (
          <div className="hifi-db-select ds-db-select-empty">
            <Database size={16} className="ds-db-empty-icon" />
            <div className="hifi-db-info">
              <span className="hifi-db-name">未连接数据源</span>
              <span className="hifi-db-version">DBFox</span>
            </div>
          </div>
        )}

        <div className="hifi-search-box">
          <Search size={14} className="hifi-search-icon" />
          <input
            type="text"
            className="hifi-search-input"
            placeholder="搜索表或字段"
            value={treeSearch}
            onChange={(event) => onTreeSearchChange(event.target.value)}
          />
        </div>

        <div className="ds-sidebar-quick-nav">
          <button
            type="button"
            onClick={openSmartQueryTab}
            className={`ds-quick-nav-item ${activeTabType === "smart-query" ? "active" : ""}`}
            aria-current={activeTabType === "smart-query" ? "page" : undefined}
          >
            <Sparkles size={14} className="ds-quick-nav-icon ds-quick-nav-icon--smart" />
            <span>智能问数</span>
          </button>
          <button
            type="button"
            onClick={openConversationHistoryTab}
            className={`ds-quick-nav-item ${activeTabType === "conversation-history" ? "active" : ""}`}
            aria-current={activeTabType === "conversation-history" ? "page" : undefined}
          >
            <MessageSquare size={14} className="ds-quick-nav-icon ds-quick-nav-icon--history" />
            <span>对话历史</span>
          </button>
        </div>

        <ScrollArea className="hifi-tree-container ds-tree-scroll-area">
          {error && <div className="ds-tree-status ds-tree-status--error" role="alert">{getUserErrorMessage(error, "表结构加载失败，请重试。")}</div>}
          {loading && <div className="ds-tree-status" role="status">正在加载表结构…</div>}
          {!loading && !error && !activeDatasource && <div className="ds-tree-status">暂无数据源，请先创建连接。</div>}

          {activeDatasource && (
            <button
              type="button"
              className="hifi-tree-node ds-schema-node"
              onClick={() => setSchemaCollapsed((v) => !v)}
              onContextMenu={(event) => onNodeContextMenu(event, "schema", activeDatasource.database_name || activeDatasource.name)}
              aria-expanded={!schemaCollapsed}
            >
              <ChevronDown
                size={14}
                className={`ds-group-chevron ds-schema-chevron ${schemaCollapsed ? "ds-group-chevron-collapsed" : ""}`}
              />
              <Database size={14} className="ds-schema-icon" />
              <span>{activeDatasource.database_name || activeDatasource.name}</span>
            </button>
          )}

          {!schemaCollapsed && Object.entries(groupedTables).map(([moduleName, moduleTables]) => {
            const groupCollapsed = collapsedGroups.has(moduleName);
            return (
              <div key={moduleName} className="ds-tree-group">
                <button type="button" className="hifi-tree-node ds-tree-group-header" onClick={() => toggleGroup(moduleName)} aria-expanded={!groupCollapsed}>
                  <ChevronDown
                    size={12}
                    className={`ds-group-chevron ds-group-chevron-muted ${groupCollapsed ? "ds-group-chevron-collapsed" : ""}`}
                  />
                  <span className="ds-tree-group-label">{moduleName}</span>
                </button>

                {!groupCollapsed && moduleTables.map((table) => {
                  const isSelected = selectedTables.includes(table.table_name);
                  return (
                    <button
                      type="button"
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
                      aria-pressed={isSelected}
                    >
                      <span className="hifi-tree-indent" />
                      <FileText size={13} className="ds-tree-table-icon" />
                      <span className="ds-tree-table-name" title={table.table_comment}>{table.table_name}</span>
                    </button>
                  );
                })}
              </div>
            );
          })}

          {activeDatasource && !loading && Object.keys(groupedTables).length === 0 && (
            <div className="ds-tree-status">没有匹配的表。请先同步表结构或调整搜索词。</div>
          )}
        </ScrollArea>
      </div>
    </section>
  );
}
