import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronDown,
  Folder,
  FolderOpen,
  MessageSquare,
  Plus,
  Settings,
} from "lucide-react";
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
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useConversationStore } from "../../stores/conversationStore";
import { useDatasourceState } from "../datasource/useDatasourceState";
import { useProjectState } from "../projects/useProjectState";
import { getUserErrorMessage } from "../../lib/api/client";
import type { ResourceConnectorContribution } from "../resources/types";
import type { ConversationSummary } from "../../types/conversation";
import "../datasource/DataSourceTree.css";

interface ProjectResourceSidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNewProject: () => void;
  onOpenSettings: () => void;
  connectors: readonly ResourceConnectorContribution[];
}

export function ProjectResourceSidebar({
  collapsed,
  onToggleCollapse,
  onNewProject,
  onOpenSettings,
  connectors,
}: ProjectResourceSidebarProps) {
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const setActiveProject = useWorkspaceStore((s) => s.setActiveProject);
  const showSmartQueryHome = useWorkspaceStore((s) => s.showSmartQueryHome);
  const openConversationCenter = useWorkspaceStore((s) => s.openConversationCenter);

  const { projects, loadingProjects } = useProjectState(activeProjectId);

  const { datasources, setActiveDatasourceId } = useDatasourceState(activeProjectId);

  const summaries = useConversationStore((s) => s.summaries);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const openConversation = useConversationStore((s) => s.openConversation);

  const restoredConversationProjectRef = useRef("");
  const [conversationError, setConversationError] = useState("");
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | undefined>();

  const activeConnectorId =
    selectedConnectorId && connectors.some((c) => c.id === selectedConnectorId)
      ? selectedConnectorId
      : connectors[0]?.id;

  // Auto-select first project
  useEffect(() => {
    if (activeProjectId || loadingProjects || projects.length === 0) return;
    setActiveProject(projects[0].id);
  }, [activeProjectId, loadingProjects, projects, setActiveProject]);

  // Restore conversation for active project
  useEffect(() => {
    if (!activeProjectId) return;
    if (restoredConversationProjectRef.current === activeProjectId) return;
    restoredConversationProjectRef.current = activeProjectId;
    const storedConversationId = useWorkspaceStore.getState().projectShell[activeProjectId]?.activeConversationId;
    if (!storedConversationId) return;
    void openConversation(storedConversationId)
      .then((detail) => {
        if (activeProjectId === useWorkspaceStore.getState().activeProjectId) {
          openConversationCenter(detail.id);
          useWorkspaceStore.getState().setProjectActiveConversation(activeProjectId, detail.id);
        }
      })
      .catch((openError) => {
        setConversationError(getUserErrorMessage(openError, "对话恢复失败，请重试。"));
      });
  }, [activeProjectId, openConversation, openConversationCenter]);

  const conversationsForProject = useMemo(() => {
    if (!activeProjectId) return [];
    const datasourceIds = new Set(
      datasources.filter((item) => item.project_id === activeProjectId).map((item) => item.id),
    );
    const seen = new Set<string>();
    const result: ConversationSummary[] = [];
    for (const c of summaries) {
      const matchesDirect = c.project_id === activeProjectId;
      const matchesLegacy = (c.project_id === null || c.project_id === undefined)
        && Boolean(c.datasource_id && datasourceIds.has(c.datasource_id));
      if ((matchesDirect || matchesLegacy) && !seen.has(c.id)) {
        seen.add(c.id);
        result.push(c);
      }
    }
    return result;
  }, [activeProjectId, datasources, summaries]);

  const handleOpenConversation = async (conversationId: string) => {
    setConversationError("");
    try {
      await openConversation(conversationId);
      openConversationCenter(conversationId);
      if (activeProjectId) useWorkspaceStore.getState().setProjectActiveConversation(activeProjectId, conversationId);
    } catch (openError) {
      setConversationError(getUserErrorMessage(openError, "对话加载失败，请重试。"));
    }
  };

  const handleSelectProject = (projectId: string) => {
    setActiveProject(projectId);
    const firstDatasource = datasources.find((item) => item.project_id === projectId);
    if (firstDatasource) setActiveDatasourceId(firstDatasource.id);
  };

  const handleNewProjectConversation = (projectId: string) => {
    setActiveProject(projectId);
    const firstDatasource = datasources.find((item) => item.project_id === projectId);
    if (firstDatasource) setActiveDatasourceId(firstDatasource.id);
    showSmartQueryHome();
  };

  const addableConnectors = useMemo(
    () => connectors.filter((c) => c.onAdd && c.addLabel),
    [connectors],
  );
  const activeConnector = connectors.find((c) => c.id === activeConnectorId);

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

  return (
    <section className="hifi-col hifi-sidebar-col ds-tree-main">
      <div className="hifi-sidebar-panel">
        <div className="hifi-sidebar-header ds-tree-header-row">
          <div className="ds-tree-actions">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={onNewProject}
                  aria-label="新建项目"
                  className="ds-tree-icon-btn"
                >
                  <Plus size={15} strokeWidth={1.5} />
                </button>
              </TooltipTrigger>
              <TooltipContent>新建项目</TooltipContent>
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

          {/* Project list */}
          <div className="ds-entity-list">
            {loadingProjects && <div className="ds-tree-status">正在读取项目…</div>}
            {!loadingProjects && projects.length === 0 && (
              <div className="ds-tree-status">还没有项目。点击右上角 + 选择电脑上的文件夹。</div>
            )}
            {projects.map((project) => {
              const isActive = project.id === activeProjectId;
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
                  </div>
                </div>
              );
            })}
          </div>

          {/* Conversations (Core) */}
          {activeProjectId ? (
            <div className="ds-resource-section">
              <div className="ds-conversation-group-header ds-resource-header">
                <MessageSquare size={13} aria-hidden="true" />
                <span className="ds-resource-header-label">对话</span>
                {conversationsForProject.length > 0 && (
                  <span className="ds-conversation-count">{conversationsForProject.length}</span>
                )}
              </div>
              <div className="ds-entity-row__content">
                {conversationsForProject.length === 0 ? (
                  <div className="ds-tree-status">暂无对话，点击 + 开始新对话。</div>
                ) : (
                  conversationsForProject.map((conversation) => (
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
            </div>
          ) : null}

          {/* Resources (Connector Slot) */}
          {activeProjectId && connectors.length > 0 ? (
            <div className="ds-resource-section">
              <div className="ds-resource-header">
                {/* Connector selector tabs */}
                <div className="ds-entity-sub-switch">
                  {connectors.map((connector) => (
                    <button
                      key={connector.id}
                      type="button"
                      className={`ds-entity-sub-switch__button ${activeConnectorId === connector.id ? "is-active" : ""}`}
                      onClick={() => setSelectedConnectorId(connector.id)}
                    >
                      {connector.icon}
                      <span>{connector.title}</span>
                    </button>
                  ))}
                </div>

                {/* Add Resource menu */}
                {addableConnectors.length > 0 ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        className="ds-tree-icon-btn ds-add-resource-btn"
                        aria-label="添加资源"
                      >
                        <Plus size={13} />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {addableConnectors.map((connector) => (
                        <DropdownMenuItem
                          key={connector.id}
                          onClick={() => connector.onAdd?.({ projectId: activeProjectId })}
                        >
                          {connector.addLabel}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </div>

              {/* Active connector content */}
              <div>
                {activeConnector ? (
                  activeConnector.render({ projectId: activeProjectId })
                ) : (
                  <div className="ds-tree-status">没有可用的资源连接器。</div>
                )}
              </div>
            </div>
          ) : null}
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
