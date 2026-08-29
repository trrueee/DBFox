import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertCircle,
  ChevronRight,
  Folder,
  Home,
  PackageOpen,
  PanelLeftClose,
  Plus,
  Settings2,
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
} from "../../components/ui";
import { getUserErrorMessage } from "../../lib/api/client";
import { useConversationStore } from "../../stores/conversationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { selectActiveConversationId } from "../../stores/workspaceStore";
import { useProjectState } from "../projects/useProjectState";
import type { ConversationSummary } from "../../types/conversation";
import type { ResourceConnectorContribution } from "./types";
import { ResourceViewContainer } from "./ResourceViewContainer";
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
  const { projects, loadingProjects, projectError } = useProjectState(activeProjectId);
  const summaries = useConversationStore((state) => state.summaries);
  const openConversation = useConversationStore((state) => state.openConversation);
  const activeConversationId = useWorkspaceStore(selectActiveConversationId);
  const [navigationError, setNavigationError] = useState<unknown | null>(null);
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (activeProjectId || loadingProjects || projects.length === 0) return;
    setActiveProject(projects[0].id);
    useWorkspaceStore.getState().showSmartQueryHome();
  }, [activeProjectId, loadingProjects, projects, setActiveProject]);

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
          <CollapsedAction label="展开导航" onClick={onToggleCollapse} icon={<ChevronRight />} />
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
          <span className="product-sidebar__title">工作</span>
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
          onClick={() => showSmartQueryHome()}
        />
        <SidebarNavRow
          icon={<Home />}
          label="主页"
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
                  <Button type="button" variant="ghost" size="icon-sm" onClick={onNewProject} aria-label="新建项目">
                    <Plus size={14} aria-hidden="true" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>新建项目</TooltipContent>
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
  onOpenConversation: (conversationId: string) => void;
}

/**
 * One project node: clicking the row focuses the project and toggles the group;
 * the hover gear opens project management. Conversations (preview + overflow)
 * and resource sections sit directly under the row. Conversation text aligns
 * with the project's label through an empty icon column — no conversation icon.
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
  onOpenConversation,
}: ProjectGroupProps) {
  const [showAllConversations, setShowAllConversations] = useState(false);

  const visibleConversations = showAllConversations
    ? conversations
    : conversations.slice(0, CONVERSATION_PREVIEW_LIMIT);
  const hiddenCount = conversations.length - visibleConversations.length;

  return (
    <div className="project-group">
      <div className="project-group__header" data-active={isActive || undefined}>
        <SidebarNavRow
          className="project-group__name"
          icon={<Folder />}
          label={project.name}
          active={isActive}
          onClick={onSelect}
          title={project.name}
        />
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="project-group__manage"
              aria-label={`管理项目 ${project.name}`}
              onClick={(event) => {
                event.stopPropagation();
                onOpenManagement();
              }}
            >
              <Settings2 size={14} aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">项目管理与资源</TooltipContent>
        </Tooltip>
      </div>
      {expanded ? (
        <div className="project-group__body">
          {visibleConversations.map((conversation) => (
            <SidebarNavRow
              key={conversation.id}
              icon={<span aria-hidden="true" />}
              label={conversation.title || "未命名任务"}
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
            <p className="project-group__empty">这个项目还没有对话。</p>
          ) : null}
          <ResourceViewContainer projectId={project.id} connectors={connectors} showGroupLabel={false} />
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
