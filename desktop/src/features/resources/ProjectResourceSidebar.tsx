import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertCircle,
  ChevronRight,
  ChevronDown,
  PackageOpen,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  MoreHorizontal,
  Settings,
} from "lucide-react";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarNavRow,
  Button,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  ErrorDetails,
  ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator,
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
} from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import { useConversationStore } from "../../stores/conversationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { selectActiveConversationId } from "../../stores/workspaceStore";
import { useProjectState } from "../projects/useProjectState";
import type { ConversationSummary } from "../../types/conversation";
import type { ResourceConnectorContribution } from "./types";
import { openProjectWorkbench } from "./ProjectWorkbench";
import { ResourceIcon } from "../../components/resources/resourcePresentation";
import { conversationTitle } from "../conversation/conversationTitle";
import "./ProjectResourceSidebar.css";

/** Conversations shown per project before the "show more" overflow. */
const CONVERSATION_PREVIEW_LIMIT = 5;

interface ProjectResourceSidebarProps {
  connectors: readonly ResourceConnectorContribution[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNewProject: () => void;
  onOpenSettings: () => void;
  onOpenExtensions: () => void;
}

export function ProjectResourceSidebar({
  connectors,
  collapsed,
  onToggleCollapse,
  onNewProject,
  onOpenSettings,
  onOpenExtensions,
}: ProjectResourceSidebarProps) {
  const activeProjectId = useWorkspaceStore((state) => state.activeProjectId);
  const setActiveProject = useWorkspaceStore((state) => state.setActiveProject);
  const showSmartQueryHome = useWorkspaceStore((state) => state.showSmartQueryHome);
  const showProjectOverview = useWorkspaceStore((state) => state.showProjectOverview);
  const openConversationCenter = useWorkspaceStore((state) => state.openConversationCenter);
  const mainSurface = useWorkspaceStore((state) => (
    state.activeProjectId ? state.mainSurfaceByProject[state.activeProjectId] : undefined
  ));
  const { projects, loadingProjects, projectError, refreshProjects } = useProjectState(activeProjectId);
  const summaries = useConversationStore((state) => state.summaries);
  const openConversation = useConversationStore((state) => state.openConversation);
  const activeConversationId = useWorkspaceStore(selectActiveConversationId);
  const [navigationError, setNavigationError] = useState<unknown | null>(null);
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (loadingProjects || projectError || projects.some(project => project.id === activeProjectId)) return;
    setActiveProject(projects[0]?.id ?? "");
    useWorkspaceStore.getState().showSmartQueryHome();
  }, [activeProjectId, loadingProjects, projectError, projects, setActiveProject]);

  // The active project's group follows focus so its conversations stay reachable.
  useEffect(() => {
    if (!activeProjectId) return;
    setExpandedProjects((current) => (
      current[activeProjectId] ? current : { ...current, [activeProjectId]: true }
    ));
  }, [activeProjectId]);

  const conversationsByProject = useMemo(() => {
    const map = new Map<string, ConversationSummary[]>();
    for (const summary of summaries) {
      if (!summary.project_id) continue;
      const list = map.get(summary.project_id);
      if (list) list.push(summary);
      else map.set(summary.project_id, [summary]);
    }
    return map;
  }, [summaries]);

  /** Row click: focus the project and toggle its group. No forced surface change —
      an untouched project falls back to the new-task home. */
  const selectProject = (projectId: string) => {
    if (projectId !== activeProjectId) setActiveProject(projectId);
    setExpandedProjects((current) => ({ ...current, [projectId]: !(current[projectId] ?? projectId === activeProjectId) }));
  };

  const openManagement = (projectId: string) => {
    if (projectId !== activeProjectId) setActiveProject(projectId);
    showProjectOverview();
  };

  const openRecent = async (conversationId: string, projectId: string) => {
    setNavigationError(null);
    try {
      if (projectId !== activeProjectId) setActiveProject(projectId);
      await openConversation(conversationId);
      if (useWorkspaceStore.getState().activeProjectId !== projectId) return;
      openConversationCenter(conversationId);
      useWorkspaceStore.getState().setProjectActiveConversation(projectId, conversationId);
    } catch (error) {
      setNavigationError(error);
    }
  };

  if (collapsed) {
    return (
      <Sidebar className="product-sidebar product-sidebar--collapsed" aria-label="主导航">
        <SidebarHeader>
          <CollapsedAction label="展开导航" onClick={onToggleCollapse} icon={<PanelLeftOpen />} />
          <CollapsedAction label="新任务" onClick={() => showSmartQueryHome()} icon={<Plus />} primary />
        </SidebarHeader>
        <SidebarFooter>
          <CollapsedAction label="扩展" onClick={onOpenExtensions} icon={<PackageOpen />} />
          <CollapsedAction label="设置" onClick={onOpenSettings} icon={<Settings />} />
        </SidebarFooter>
      </Sidebar>
    );
  }

  return (
    <Sidebar className="product-sidebar" aria-label="主导航">
      <SidebarHeader>
        <div className="product-sidebar__topline">
          <span className="product-sidebar__title">DBFox</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button type="button" variant="ghost" size="icon-sm" onClick={onToggleCollapse} aria-label="收起导航">
                <PanelLeftClose size={16} aria-hidden="true" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>收起导航</TooltipContent>
          </Tooltip>
        </div>
        <SidebarNavRow
          className="product-sidebar__new-task"
          icon={<Plus />}
          label="新任务"
          active={mainSurface?.kind === "new-conversation"}
          onClick={() => showSmartQueryHome()}
        />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel
            action={(
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button type="button" variant="ghost" size="icon-sm" onClick={onNewProject} aria-label="打开文件夹">
                    <Plus size={14} aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>打开文件夹</TooltipContent>
              </Tooltip>
            )}
          >
            项目
          </SidebarGroupLabel>
          {loadingProjects ? <p className="product-sidebar__status">正在载入项目…</p> : null}
          {projectError ? (
              <Alert className="product-sidebar__alert" variant="destructive">
                <AlertCircle aria-hidden="true" />
                <AlertTitle>读取项目失败</AlertTitle>
                <AlertDescription>
                  <span>{getUserErrorMessage(projectError, "读取项目失败，请重试。")}</span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => void refreshProjects()}>重试读取项目</Button>
                  <ErrorDetails error={projectError} />
                </AlertDescription>
            </Alert>
          ) : null}
          {navigationError ? (
              <Alert className="product-sidebar__alert" variant="destructive">
                <AlertCircle aria-hidden="true" />
                <AlertTitle>工作加载失败</AlertTitle>
                <AlertDescription>
                  <span>{getUserErrorMessage(navigationError, "工作加载失败，请重试。")}</span>
                  <ErrorDetails error={navigationError} />
                </AlertDescription>
            </Alert>
          ) : null}
          {projects.map((project) => (
            <ProjectGroup
              key={project.id}
              project={project}
              expanded={expandedProjects[project.id] ?? project.id === activeProjectId}
              conversations={conversationsByProject.get(project.id) ?? []}
              connectors={connectors}
              isActive={project.id === activeProjectId}
              isConversationActive={project.id === activeProjectId
                && mainSurface?.kind === "conversation"
                ? activeConversationId
                : null}
              onSelect={() => selectProject(project.id)}
              onOpenManagement={() => openManagement(project.id)}
              onNewConversation={() => { setActiveProject(project.id); showSmartQueryHome(); }}
              onOpenWorkbench={(connector, configure) => {
                setActiveProject(project.id);
                void Promise.resolve().then(() => openProjectWorkbench(connector, project.id))
                  .then(() => configure ? connector.onAdd?.({ projectId: project.id }) : undefined).catch(setNavigationError);
              }}
              onOpenConversation={(conversationId) => void openRecent(conversationId, project.id)}
            />
          ))}
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarNavRow icon={<PackageOpen />} label="扩展" onClick={onOpenExtensions} />
        <SidebarNavRow icon={<Settings />} label="设置" onClick={onOpenSettings} />
      </SidebarFooter>
    </Sidebar>
  );
}

interface ProjectGroupProps {
  project: { id: string; name: string };
  expanded: boolean;
  conversations: ConversationSummary[];
  connectors: readonly ResourceConnectorContribution[];
  isActive: boolean;
  isConversationActive: string | null;
  onSelect: () => void;
  onOpenManagement: () => void;
  onNewConversation: () => void;
  onOpenWorkbench: (connector: ResourceConnectorContribution, configure?: boolean) => void;
  onOpenConversation: (conversationId: string) => void;
}

/**
 * Folder projects contain conversations. Capabilities open from the shared
 * context menu and visible menu button into their registered Dock workbenches.
 */
function ProjectGroup({
  project,
  expanded,
  conversations,
  connectors,
  isActive,
  isConversationActive,
  onSelect,
  onOpenManagement,
  onNewConversation,
  onOpenWorkbench,
  onOpenConversation,
}: ProjectGroupProps) {
  const [showAllConversations, setShowAllConversations] = useState(false);

  const visibleConversations = showAllConversations
    ? conversations
    : conversations.slice(0, CONVERSATION_PREVIEW_LIMIT);
  const hiddenCount = conversations.length - visibleConversations.length;
  const actions = [
    { label: "新对话", icon: <Plus size={16} aria-hidden="true" />, run: onNewConversation },
    ...connectors.flatMap(connector => [
      { label: `查看${connector.title}`, icon: connector.icon, run: () => onOpenWorkbench(connector) },
      ...(connector.onAdd ? [{ label: connector.addLabel ?? `添加${connector.title}`, icon: <Plus size={16} aria-hidden="true" />, run: () => onOpenWorkbench(connector, true) }] : []),
    ]),
  ];

  return (
    <div className="project-group">
      <ContextMenu><ContextMenuTrigger asChild><div className="project-group__header" data-active={isActive || undefined}>
        <SidebarNavRow
          className="project-group__name"
          icon={expanded ? <ChevronDown /> : <ChevronRight />}
          label={<span className="project-group__identity"><ResourceIcon kind="folder" expanded={expanded} size={16} /><span>{project.name}</span></span>}
          active={isActive}
          aria-expanded={expanded}
          onClick={onSelect}
          title={project.name}
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="project-group__manage"
              aria-label={`管理项目 ${project.name}`}
            >
              <MoreHorizontal size={16} aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">{actions.map(action => <DropdownMenuItem key={action.label} onSelect={action.run}>{action.icon}{action.label}</DropdownMenuItem>)}<DropdownMenuSeparator /><DropdownMenuItem onSelect={onOpenManagement}><Settings size={16} aria-hidden="true" />项目设置</DropdownMenuItem></DropdownMenuContent>
        </DropdownMenu>
      </div></ContextMenuTrigger><ContextMenuContent>{actions.map(action => <ContextMenuItem key={action.label} onSelect={action.run}>{action.icon}{action.label}</ContextMenuItem>)}<ContextMenuSeparator /><ContextMenuItem onSelect={onOpenManagement}><Settings size={16} aria-hidden="true" />项目设置</ContextMenuItem></ContextMenuContent></ContextMenu>
      {expanded ? (
        <div className="project-group__body">
          {visibleConversations.map((conversation) => (
            <SidebarNavRow
              key={conversation.id}
              icon={<span aria-hidden="true" />}
              label={conversationTitle(conversation.title)}
              meta={formatRelativeTime(conversation.updated_at)}
              active={conversation.id === isConversationActive}
              onClick={() => onOpenConversation(conversation.id)}
              title={conversation.title}
            />
          ))}
          {hiddenCount > 0 ? (
            <button
              type="button"
              className="project-group__more"
              onClick={() => setShowAllConversations(true)}
            >
              显示更多
            </button>
          ) : null}
          {showAllConversations && conversations.length > CONVERSATION_PREVIEW_LIMIT ? (
            <button
              type="button"
              className="project-group__more"
              onClick={() => setShowAllConversations(false)}
            >
              收起
            </button>
          ) : null}
          {conversations.length === 0 ? (
            <p className="project-group__empty">暂无对话</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Compact relative time for the sidebar rows: 刚刚 / 5分钟 / 2小时 / 3天 / 8月21日. */
function formatRelativeTime(value?: string | null): string {
  if (!value) return "";
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return "";
  const elapsedMinutes = Math.floor((Date.now() - time) / 60000);
  if (elapsedMinutes < 1) return "刚刚";
  if (elapsedMinutes < 60) return `${elapsedMinutes}分钟`;
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours}小时`;
  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays < 30) return `${elapsedDays}天`;
  return new Date(value).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function CollapsedAction({
  label,
  onClick,
  icon,
  primary = false,
}: {
  label: string;
  onClick: () => void;
  icon: ReactNode;
  primary?: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={primary ? "default" : "ghost"}
          size="icon-sm"
          className="product-sidebar__collapsed-action"
          onClick={onClick}
          aria-label={label}
        >
          {icon}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}
