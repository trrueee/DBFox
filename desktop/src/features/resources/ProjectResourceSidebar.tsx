import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  const [expandedConnectors, setExpandedConnectors] = useState<Record<string, boolean>>({});

  // Host owns section chrome (expand/collapse); DLC only contributes content.
  // Default: first connector expanded, the rest collapsed until the user opens them.
  const toggleConnector = useCallback((connectorId: string, currentExpanded: boolean) => {
    setExpandedConnectors((prev) => ({ ...prev, [connectorId]: !currentExpanded }));
  }, []);

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
    return summaries.filter((conversation) => conversation.project_id === activeProjectId);
  }, [activeProjectId, summaries]);

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

  const [chatsCollapsed, setChatsCollapsed] = useState(false);
  const [showAllChats, setShowAllChats] = useState(false);
  const RECENT_CHATS_LIMIT = 6;

  const displayedConversations = useMemo(() => {
    if (showAllChats) return conversationsForProject;
    return conversationsForProject.slice(0, RECENT_CHATS_LIMIT);
  }, [conversationsForProject, showAllChats]);

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? projects[0] ?? null;

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
          {projects.length > 1 ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button type="button" className="ds-workspace-identity-trigger" aria-label="切换项目">
                  <FolderOpen size={14} className="ds-workspace-identity-icon" />
                  <span className="ds-workspace-identity-name">{activeProject?.name || "工作区"}</span>
                  <ChevronDown size={12} className="ds-workspace-identity-chevron" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {projects.map((project) => (
                  <DropdownMenuItem
                    key={project.id}
                    onClick={() => handleSelectProject(project.id)}
                  >
                    <Folder size={14} className="ds-project-dropdown-icon" />
                    <span>{project.name}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <div className="ds-workspace-identity">
              <FolderOpen size={14} className="ds-workspace-identity-icon" />
              <span className="ds-workspace-identity-name">{activeProject?.name || "工作区"}</span>
            </div>
          )}

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

          {/* Conversations (Core) */}
          {activeProjectId ? (
            <div className="ds-resource-section">
              <div className="ds-resource-header ds-resource-header--collapsible">
                <button
                  type="button"
                  className="ds-section-toggle-btn"
                  onClick={() => setChatsCollapsed((c) => !c)}
                  aria-expanded={!chatsCollapsed}
                >
                  <ChevronDown
                    size={12}
                    aria-hidden="true"
                    className={`ds-section-chevron ${chatsCollapsed ? "is-collapsed" : ""}`}
                  />
                  <MessageSquare size={13} aria-hidden="true" />
                  <span className="ds-resource-header-label">对话</span>
                </button>
                {conversationsForProject.length > 0 && (
                  <span className="ds-conversation-count">{conversationsForProject.length}</span>
                )}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="ds-tree-icon-btn ds-section-add-btn"
                      aria-label="新对话"
                      onClick={() => handleNewProjectConversation(activeProjectId)}
                    >
                      <Plus size={13} />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>新对话</TooltipContent>
                </Tooltip>
              </div>

              {!chatsCollapsed && (
                <div className="ds-section-content">
                  {conversationsForProject.length === 0 ? (
                    <div className="ds-tree-status">暂无对话，点击 + 开始新对话。</div>
                  ) : (
                    <>
                      {displayedConversations.map((conversation) => (
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
                      ))}
                      {conversationsForProject.length > RECENT_CHATS_LIMIT && (
                        <button
                          type="button"
                          className="ds-tree-more-btn"
                          onClick={() => setShowAllChats((prev) => !prev)}
                        >
                          {showAllChats ? "收起" : `查看全部 ${conversationsForProject.length} 个对话`}
                        </button>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          ) : null}

          {/* Resources (Host-owned sections; connectors contribute content only) */}
          {activeProjectId && connectors.length > 0 ? (
            <div className="ds-resource-section">
              <div className="ds-resource-header">
                <span className="ds-resource-header-label">资源</span>

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

              <div className="ds-connector-sections">
                {connectors.map((connector, index) => {
                  const isExpanded = expandedConnectors[connector.id] ?? index === 0;
                  return (
                    <div key={connector.id} className="ds-connector-section">
                      <button
                        type="button"
                        className="ds-connector-section__header"
                        aria-expanded={isExpanded}
                        onClick={() => toggleConnector(connector.id, isExpanded)}
                      >
                        <ChevronDown
                          size={12}
                          aria-hidden="true"
                          className={`ds-connector-section__chevron ${isExpanded ? "" : "is-collapsed"}`}
                        />
                        {connector.icon}
                        <span className="ds-connector-section__title">{connector.title}</span>
                      </button>
                      {isExpanded ? (
                        <div className="ds-connector-section__content">
                          {connector.render({ projectId: activeProjectId })}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
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
