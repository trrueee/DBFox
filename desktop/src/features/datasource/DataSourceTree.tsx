import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import {
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  Folder,
  FolderOpen,
  MessageSquare,
  Plus,
  Settings,
} from "lucide-react";
import {
  ScrollArea,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "../../components/ui";
import { useDatasourceState } from "./useDatasourceState";
import { useProjectState } from "../projects/useProjectState";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useWorkspaceFileStore } from "../../stores/workspaceFileStore";
import { useTableWorkspaceStore } from "../../stores/tableWorkspaceStore";
import { useConversationStore } from "../../stores/conversationStore";
import { getUserErrorMessage } from "../../lib/api/client";
import type { ProjectFolderEntry, ProjectFolderListing } from "../../lib/projectFolder";
import { useProjectFolderTree } from "../projects/useProjectFolderTree";
import { DatabaseBrandIcon } from "./DatabaseBrandIcon";
import { isDatabaseBrandType } from "./databaseBrandData";
import "./DataSourceTree.css";

interface DataSourceTreeProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onTableClick: (tableName: string, event: MouseEvent) => void;
  onTableDoubleClick: (tableName: string) => void;
  onNodeContextMenu: (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => void;
  onNewConnection: () => void;
  onNewProject: () => void;
  onOpenSettings: () => void;
}

type EntitySwitchValue = "conversations" | "files" | "database";

function EntitySubSwitch({
  value,
  options,
  onChange,
}: {
  value: EntitySwitchValue;
  options: { value: EntitySwitchValue; label: string; icon: typeof MessageSquare }[];
  onChange: (value: EntitySwitchValue) => void;
}) {
  return (
    <div className="ds-entity-sub-switch" role="tablist" aria-label="实体内容">
      {options.map((option) => {
        const Icon = option.icon;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={value === option.value}
            className={`ds-entity-sub-switch__button ${value === option.value ? "is-active" : ""}`}
            onClick={() => onChange(option.value)}
          >
            <Icon size={12} aria-hidden="true" />
            <span>{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

interface ProjectFileTreeNodeProps {
  entry: ProjectFolderEntry;
  depth: number;
  listings: Record<string, ProjectFolderListing | null>;
  loadingPaths: Record<string, boolean>;
  errors: Record<string, string>;
  expandedFolders: string[];
  onToggleFolder: (entry: ProjectFolderEntry) => void;
  onOpenFile: (entry: ProjectFolderEntry) => void;
}

function ProjectFileTreeNode({
  entry,
  depth,
  listings,
  loadingPaths,
  errors,
  expandedFolders,
  onToggleFolder,
  onOpenFile,
}: ProjectFileTreeNodeProps) {
  const depthClass = `ds-project-file-node--depth-${Math.min(depth, 10)}`;
  if (entry.isDir) {
    const expanded = expandedFolders.includes(entry.path);
    const listing = listings[entry.path];
    const loading = Boolean(loadingPaths[entry.path]);
    const error = errors[entry.path] ?? null;
    return (
      <div className="ds-project-file-node" role="treeitem" aria-expanded={expanded}>
        <button
          type="button"
          className={`ds-project-file-node__dir ${depthClass}`}
          onClick={() => onToggleFolder(entry)}
          title={entry.name}
        >
          {expanded ? (
            <ChevronDown size={12} className="ds-project-file-node__chevron" aria-hidden="true" />
          ) : (
            <ChevronRight size={12} className="ds-project-file-node__chevron" aria-hidden="true" />
          )}
          <Folder size={13} className="ds-project-file-node__icon" aria-hidden="true" />
          <span className="ds-project-file-node__name">{entry.name}</span>
        </button>
        {expanded ? (
          <div className="ds-project-file-node__children" role="group">
            {loading && !listing ? (
              <div className="ds-tree-status ds-project-file-node__status" role="status">正在读取…</div>
            ) : null}
            {error ? <div className="ds-tree-status ds-tree-status--error" role="alert">{error}</div> : null}
            {listing?.entries.length === 0 ? (
              <div className="ds-tree-status ds-project-file-node__status">空文件夹</div>
            ) : null}
            {listing?.entries.map((child) => (
              <ProjectFileTreeNode
                key={child.path}
                entry={child}
                depth={depth + 1}
                listings={listings}
                loadingPaths={loadingPaths}
                errors={errors}
                expandedFolders={expandedFolders}
                onToggleFolder={onToggleFolder}
                onOpenFile={onOpenFile}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={`ds-project-file-node ds-project-file-node--file ${depthClass}`}
      onClick={() => onOpenFile(entry)}
      title={entry.path}
    >
      <FileText size={13} className="ds-project-file-node__icon" aria-hidden="true" />
      <span className="ds-project-file-node__name">{entry.name}</span>
    </button>
  );
}

export function DataSourceTree({
  collapsed,
  onToggleCollapse,
  onTableClick,
  onTableDoubleClick,
  onNodeContextMenu,
  onNewConnection,
  onNewProject,
  onOpenSettings,
}: DataSourceTreeProps) {
  const sidebarEntityMode = useWorkspaceStore((s) => s.sidebarEntityMode);
  const setSidebarEntityMode = useWorkspaceStore((s) => s.setSidebarEntityMode);
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const setActiveProject = useWorkspaceStore((s) => s.setActiveProject);
  const projectSubMode = useWorkspaceStore((s) => s.projectSubMode);
  const setProjectSubMode = useWorkspaceStore((s) => s.setProjectSubMode);
  const connectionSubMode = useWorkspaceStore((s) => s.connectionSubMode);
  const setConnectionSubMode = useWorkspaceStore((s) => s.setConnectionSubMode);
  const projectShell = useWorkspaceStore((s) => s.projectShell);
  const setProjectActiveDatasource = useWorkspaceStore((s) => s.setProjectActiveDatasource);
  const setProjectActiveConversation = useWorkspaceStore((s) => s.setProjectActiveConversation);
  const showSmartQueryHome = useWorkspaceStore((s) => s.showSmartQueryHome);
  const openConversationCenter = useWorkspaceStore((s) => s.openConversationCenter);
  const openDockFile = useWorkspaceFileStore((s) => s.openFile);

  const {
    datasources,
    activeDatasourceId,
    activeDatasource,
    setActiveDatasourceId,
    tables,
    loadingSchema: loading,
    schemaError: error,
  } = useDatasourceState();
  const { projects, loadingProjects } = useProjectState(activeProjectId);
  const activeProject = projects.find((project) => project.id === activeProjectId) ?? null;
  const {
    listings: folderListings,
    loadingPaths: folderLoadingPaths,
    errors: folderErrors,
    expandedFolders,
    loadFolder,
    toggleFolder,
  } = useProjectFolderTree();

  const summaries = useConversationStore((s) => s.summaries);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const openConversation = useConversationStore((s) => s.openConversation);
  const selectedTables = useTableWorkspaceStore((s) => s.selectedTables);

  const restoredConversationProjectRef = useRef<string>("");
  const [schemaCollapsed, setSchemaCollapsed] = useState(false);
  const [conversationError, setConversationError] = useState("");

  useEffect(() => {
    if (activeProjectId || loadingProjects || projects.length === 0) return;
    setActiveProject(projects[0].id);
  }, [activeProjectId, loadingProjects, projects, setActiveProject]);

  useEffect(() => {
    if (!activeProjectId) return;
    const stored = projectShell[activeProjectId];
    if (!stored) return;
    if (
      stored.activeDatasourceId
      && stored.activeDatasourceId !== activeDatasourceId
      && datasources.some((item) => item.id === stored.activeDatasourceId)
    ) {
      setActiveDatasourceId(stored.activeDatasourceId);
    }
  }, [activeProjectId, activeDatasourceId, datasources, projectShell, setActiveDatasourceId]);

  useEffect(() => {
    if (!activeProjectId) return;
    if (restoredConversationProjectRef.current === activeProjectId) return;
    restoredConversationProjectRef.current = activeProjectId;
    const storedConversationId = projectShell[activeProjectId]?.activeConversationId;
    if (!storedConversationId) return;
    void openConversation(storedConversationId)
      .then((detail) => {
        if (activeProjectId === useWorkspaceStore.getState().activeProjectId) {
          openConversationCenter(detail.id);
          setProjectActiveConversation(activeProjectId, detail.id);
        }
      })
      .catch((openError) => {
        setConversationError(getUserErrorMessage(openError, "对话恢复失败，请重试。"));
      });
  }, [activeProjectId, openConversation, openConversationCenter, projectShell, setProjectActiveConversation]);

  const activeProjectSubMode = activeProject
    ? projectSubMode[activeProject.id] ?? "conversations"
    : "conversations";
  const workspaceRoot = activeProject?.workspace_root?.trim() || "";

  useEffect(() => {
    if (sidebarEntityMode !== "projects" || activeProjectSubMode !== "files" || !workspaceRoot) return;
    void loadFolder(workspaceRoot);
  }, [activeProjectSubMode, loadFolder, sidebarEntityMode, workspaceRoot]);

  const handleOpenProjectFile = useCallback(
    (entry: ProjectFolderEntry) => {
      if (!activeProject) return;
      openDockFile(entry.path, entry.name, activeProject.id);
    },
    [activeProject, openDockFile],
  );

  const visibleTables = typeof tables === "object" && Array.isArray(tables) ? tables : [];

  const conversationsForDatasource = (datasourceId: string) =>
    summaries.filter((conversation) => conversation.datasource_id === datasourceId);

  const conversationsForProject = (projectId: string) => {
    const datasourceIds = new Set(
      datasources.filter((item) => item.project_id === projectId).map((item) => item.id),
    );
    return summaries.filter((conversation) => datasourceIds.has(conversation.datasource_id));
  };

  const handleOpenConversation = async (conversationId: string) => {
    setConversationError("");
    try {
      await openConversation(conversationId);
      openConversationCenter(conversationId);
      if (activeProjectId) setProjectActiveConversation(activeProjectId, conversationId);
    } catch (openError) {
      setConversationError(getUserErrorMessage(openError, "对话加载失败，请重试。"));
    }
  };

  const handleNewProjectConversation = (projectId: string) => {
    setActiveProject(projectId);
    const firstDatasource = datasources.find((item) => item.project_id === projectId);
    if (firstDatasource) setActiveDatasourceId(firstDatasource.id);
    showSmartQueryHome();
  };

  const handleNewConnectionConversation = (datasourceId: string) => {
    setActiveDatasourceId(datasourceId);
    showSmartQueryHome();
  };

  const handleSelectProject = (projectId: string) => {
    setActiveProject(projectId);
    const firstDatasource = datasources.find((item) => item.project_id === projectId);
    if (firstDatasource) setActiveDatasourceId(firstDatasource.id);
  };

  const handleSelectConnection = (datasourceId: string) => {
    setActiveDatasourceId(datasourceId);
    if (activeProjectId) setProjectActiveDatasource(activeProjectId, datasourceId);
  };

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
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button" onClick={onOpenSettings} aria-label="打开设置" className="ds-tree-expand-btn ds-tree-collapsed-settings">
              <Settings size={15} />
            </button>
          </TooltipTrigger>
          <TooltipContent>设置</TooltipContent>
        </Tooltip>
      </section>
    );
  }

  const projectConversationOptions = [
    { value: "conversations" as const, label: "对话", icon: MessageSquare },
    { value: "files" as const, label: "文件", icon: FileText },
  ];
  const connectionConversationOptions = [
    { value: "conversations" as const, label: "对话", icon: MessageSquare },
    { value: "database" as const, label: "数据库", icon: Database },
  ];

  return (
    <section className="hifi-col hifi-sidebar-col ds-tree-main">
      <div className="hifi-sidebar-panel">
        <div className="hifi-sidebar-header ds-tree-header-row">
          <div className="ds-entity-switch" role="tablist" aria-label="侧栏实体">
            <button
              type="button"
              role="tab"
              aria-selected={sidebarEntityMode === "projects"}
              className={`ds-entity-switch__button ${sidebarEntityMode === "projects" ? "is-active" : ""}`}
              onClick={() => setSidebarEntityMode("projects")}
            >
              <Folder size={13} aria-hidden="true" />
              <span>项目</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={sidebarEntityMode === "connections"}
              className={`ds-entity-switch__button ${sidebarEntityMode === "connections" ? "is-active" : ""}`}
              onClick={() => setSidebarEntityMode("connections")}
            >
              <Database size={13} aria-hidden="true" />
              <span>连接</span>
            </button>
          </div>
          <div className="ds-tree-actions">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={sidebarEntityMode === "projects" ? onNewProject : onNewConnection}
                  aria-label={sidebarEntityMode === "projects" ? "新建项目" : "新建连接"}
                  className="ds-tree-icon-btn"
                >
                  <Plus size={15} strokeWidth={1.5} />
                </button>
              </TooltipTrigger>
              <TooltipContent>{sidebarEntityMode === "projects" ? "新建项目" : "新建连接"}</TooltipContent>
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

        <ScrollArea className="hifi-tree-container ds-tree-scroll-area">
          {conversationError && <div className="ds-tree-status ds-tree-status--error" role="alert">{conversationError}</div>}

          {sidebarEntityMode === "projects" ? (
            <div className="ds-entity-list">
              {loadingProjects && <div className="ds-tree-status">正在读取项目…</div>}
              {!loadingProjects && projects.length === 0 && (
                <div className="ds-tree-status">还没有项目。点击右上角 + 选择电脑上的文件夹。</div>
              )}
              {projects.map((project) => {
                const isActive = project.id === activeProjectId;
                const subMode = projectSubMode[project.id] ?? "conversations";
                const projectConversations = conversationsForProject(project.id);
                const projectWorkspaceRoot = project.workspace_root?.trim() || "";
                return (
                  <div key={project.id} className={`ds-entity-row ${isActive ? "is-active" : ""}`}>
                    <div className="ds-entity-row__main">
                      <button
                        type="button"
                        className="ds-entity-row__trigger"
                        onClick={() => handleSelectProject(project.id)}
                        aria-current={isActive ? "page" : undefined}
                      >
                        {isActive ? (
                          <FolderOpen size={14} className="ds-entity-row__icon" />
                        ) : (
                          <Folder size={14} className="ds-entity-row__icon" />
                        )}
                        <span className="ds-entity-row__name">{project.name}</span>
                      </button>
                      <button
                        type="button"
                        className="ds-entity-row__new-conversation"
                        aria-label={`${project.name} 新对话`}
                        onClick={() => handleNewProjectConversation(project.id)}
                      >
                        <Plus size={13} />
                      </button>
                      <EntitySubSwitch
                        value={subMode}
                        options={projectConversationOptions}
                        onChange={(value) => setProjectSubMode(project.id, value as "conversations" | "files")}
                      />
                    </div>

                    {isActive && subMode === "conversations" ? (
                      <div className="ds-entity-row__content">
                        {projectConversations.length === 0 ? (
                          <div className="ds-tree-status">暂无对话，点击 + 开始新对话。</div>
                        ) : (
                          projectConversations.map((conversation) => (
                            <button
                              type="button"
                              key={conversation.id}
                              className={`hifi-tree-node ds-tree-table-row ${conversation.id === activeConversationId ? "active" : ""}`}
                              onClick={() => { void handleOpenConversation(conversation.id); }}
                              aria-current={conversation.id === activeConversationId ? "page" : undefined}
                              title={conversation.title}
                            >
                              <MessageSquare size={13} className="ds-tree-table-icon" />
                              <span className="ds-tree-table-name">{conversation.title}</span>
                            </button>
                          ))
                        )}
                      </div>
                    ) : null}

                    {isActive && subMode === "files" ? (
                      <div className="ds-entity-row__content ds-project-files">
                        {!projectWorkspaceRoot ? (
                          <div className="ds-tree-status">该项目未关联本地文件夹，编辑项目以重新选择。</div>
                        ) : folderLoadingPaths[projectWorkspaceRoot] && !folderListings[projectWorkspaceRoot] ? (
                          <div className="ds-tree-status" role="status">正在读取项目文件…</div>
                        ) : folderErrors[projectWorkspaceRoot] && !folderListings[projectWorkspaceRoot] ? (
                          <div className="ds-tree-status ds-tree-status--error" role="alert">{folderErrors[projectWorkspaceRoot]}</div>
                        ) : folderListings[projectWorkspaceRoot]?.entries.length === 0 ? (
                          <div className="ds-tree-status">这个文件夹是空的。</div>
                        ) : (
                          <div className="ds-project-file-tree" role="tree" aria-label={`${project.name} 项目文件`}>
                            {folderListings[projectWorkspaceRoot]?.entries.map((entry) => (
                              <ProjectFileTreeNode
                                key={entry.path}
                                entry={entry}
                                depth={0}
                                listings={folderListings}
                                loadingPaths={folderLoadingPaths}
                                errors={folderErrors}
                                expandedFolders={expandedFolders}
                                onToggleFolder={toggleFolder}
                                onOpenFile={handleOpenProjectFile}
                              />
                            ))}
                            {folderListings[projectWorkspaceRoot]?.truncated ? (
                              <div className="ds-tree-status ds-project-file-node__status">文件夹内容过多，只显示前 600 项。</div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="ds-entity-list">
              {!loading && !activeDatasource && datasources.length === 0 && (
                <div className="ds-tree-status">还没有连接。点击右上角 + 新建数据库连接。</div>
              )}
              {datasources.map((datasource) => {
                const isActive = datasource.id === activeDatasourceId;
                const subMode = connectionSubMode[datasource.id] ?? "database";
                const datasourceConversations = conversationsForDatasource(datasource.id);
                return (
                  <div key={datasource.id} className={`ds-entity-row ${isActive ? "is-active" : ""}`}>
                    <div className="ds-entity-row__main">
                      <button
                        type="button"
                        className="ds-entity-row__trigger"
                        onClick={() => handleSelectConnection(datasource.id)}
                        aria-current={isActive ? "page" : undefined}
                      >
                        {isDatabaseBrandType(datasource.db_type) ? (
                          <DatabaseBrandIcon dbType={datasource.db_type} size={14} className="ds-entity-row__icon" />
                        ) : (
                          <Database size={14} className="ds-entity-row__icon" />
                        )}
                        <span className="ds-entity-row__name">{datasource.name}</span>
                      </button>
                      <button
                        type="button"
                        className="ds-entity-row__new-conversation"
                        aria-label={`${datasource.name} 新对话`}
                        onClick={() => handleNewConnectionConversation(datasource.id)}
                      >
                        <Plus size={13} />
                      </button>
                      <EntitySubSwitch
                        value={subMode}
                        options={connectionConversationOptions}
                        onChange={(value) => setConnectionSubMode(datasource.id, value as "conversations" | "database")}
                      />
                    </div>

                    {isActive && subMode === "conversations" ? (
                      <div className="ds-entity-row__content">
                        {datasourceConversations.length === 0 ? (
                          <div className="ds-tree-status">暂无对话，点击 + 开始新对话。</div>
                        ) : (
                          datasourceConversations.map((conversation) => (
                            <button
                              type="button"
                              key={conversation.id}
                              className={`hifi-tree-node ds-tree-table-row ${conversation.id === activeConversationId ? "active" : ""}`}
                              onClick={() => { void handleOpenConversation(conversation.id); }}
                              aria-current={conversation.id === activeConversationId ? "page" : undefined}
                              title={conversation.title}
                            >
                              <MessageSquare size={13} className="ds-tree-table-icon" />
                              <span className="ds-tree-table-name">{conversation.title}</span>
                            </button>
                          ))
                        )}
                      </div>
                    ) : null}

                    {isActive && subMode === "database" ? (
                      <div className="ds-entity-row__content">
                        {error && <div className="ds-tree-status ds-tree-status--error" role="alert">{getUserErrorMessage(error, "表结构加载失败，请重试。")}</div>}
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
                              onContextMenu={(event) => onNodeContextMenu(event, "schema", activeDatasource?.database_name || datasource.name)}
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
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>

        <div className="ds-sidebar-footer">
          <button type="button" className="ds-settings-entry" onClick={onOpenSettings}>
            <Settings size={15} aria-hidden="true" />
            <span>设置</span>
          </button>
        </div>
      </div>
    </section>
  );
}
