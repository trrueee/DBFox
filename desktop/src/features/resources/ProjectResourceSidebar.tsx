import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useShallow } from "zustand/react/shallow";
import {
  WarningCircleIcon,
  CaretRightIcon,
  PuzzlePieceIcon,
  SidebarSimpleIcon,
  PlusIcon,
  DotsThreeIcon,
  GearIcon,
} from "@/components/icons";

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
import { ThreadBeacon } from "../conversation/ThreadBeacon";
import { threadRunStatus, runPresentation } from "../conversation/runPresentation";

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
  const threadCounts = useConversationStore(useShallow(state => {
    let running = 0;
    let waiting = 0;
    for (const summary of state.summaries) {
      if (!projects.some(project => project.id === summary.project_id)) continue;
      const priority = runPresentation(threadRunStatus(state.detailById[summary.id], summary)).priority;
      if (priority === 0) waiting += 1;
      if (priority === 1) running += 1;
    }
    return { running, waiting };
  }));

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
          <CollapsedAction label="展开导航" onClick={onToggleCollapse} icon={<SidebarSimpleIcon />} />
          <CollapsedAction label="新任务" onClick={() => showSmartQueryHome()} icon={<PlusIcon />} primary />
          {threadCounts.waiting > 0 ? <CollapsedAction label={`${threadCounts.waiting} 个对话待介入`}
            icon={<ThreadBeacon status="waiting_input" decorative />} onClick={() => {
              const state = useConversationStore.getState();
              const pending = state.summaries.find(summary => summary.project_id
                && projects.some(project => project.id === summary.project_id)
                && runPresentation(threadRunStatus(state.detailById[summary.id], summary)).priority === 0);
              if (pending?.project_id) void openRecent(pending.id, pending.project_id);
            }} /> : null}
        </SidebarHeader>
        <SidebarFooter>
          <CollapsedAction label="扩展" onClick={onOpenExtensions} icon={<PuzzlePieceIcon />} />
          <CollapsedAction label="设置" onClick={onOpenSettings} icon={<GearIcon />} />
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
                <SidebarSimpleIcon size={18} aria-hidden="true" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>收起导航</TooltipContent>
          </Tooltip>
        </div>
        <SidebarNavRow
          className="product-sidebar__new-task"
          icon={<PlusIcon />}
          label="新任务"
          active={mainSurface?.kind === "new-conversation"}
          onClick={() => showSmartQueryHome()}
        />
        {threadCounts.running + threadCounts.waiting > 0 ? <div className="product-sidebar__thread-counts" role="status" aria-label="线程状态概览">
          {threadCounts.running > 0 ? <span><ThreadBeacon status="running" decorative />{threadCounts.running} 进行中</span> : null}
          {threadCounts.waiting > 0 ? <span><ThreadBeacon status="waiting_approval" decorative />{threadCounts.waiting} 待介入</span> : null}
        </div> : null}
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel
            action={(
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button type="button" variant="ghost" size="icon-sm" onClick={onNewProject} aria-label="打开文件夹">
                    <PlusIcon size={18} aria-hidden="true" />
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
                <WarningCircleIcon aria-hidden="true" />
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
                <WarningCircleIcon aria-hidden="true" />
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
                void Promise.resolve().then(() => configure && connector.onAdd
                  ? connector.onAdd({ projectId: project.id })
                  : openProjectWorkbench(connector, project.id)).catch(setNavigationError);
              }}
              onOpenConversation={(conversationId) => void openRecent(conversationId, project.id)}
            />
          ))}
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarNavRow icon={<PuzzlePieceIcon />} label="扩展" onClick={onOpenExtensions} />
        <SidebarNavRow icon={<GearIcon />} label="设置" onClick={onOpenSettings} />
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
  const statuses = useConversationStore(useShallow(state => Object.fromEntries(conversations.map(conversation => [
    conversation.id, threadRunStatus(state.detailById[conversation.id], conversation),
  ]))));
  const orderedConversations = [...conversations].sort((left, right) => runPresentation(statuses[left.id]).priority - runPresentation(statuses[right.id]).priority);
  const activeCount = conversations.filter(conversation => runPresentation(statuses[conversation.id]).priority < 2).length;
  const waitingCount = conversations.filter(conversation => runPresentation(statuses[conversation.id]).priority === 0).length;
  const visibleConversations = showAllConversations
    ? orderedConversations
    : orderedConversations.slice(0, Math.max(CONVERSATION_PREVIEW_LIMIT, activeCount));
  const hiddenCount = conversations.length - visibleConversations.length;
  const actions = [
    { label: "新对话", icon: <PlusIcon size={16} aria-hidden="true" />, run: onNewConversation },
    ...connectors.flatMap(connector => [
      { label: `查看${connector.title}`, icon: connector.icon, run: () => onOpenWorkbench(connector) },
      ...(connector.onAdd ? [{ label: connector.addLabel ?? `添加${connector.title}`, icon: <PlusIcon size={16} aria-hidden="true" />, run: () => onOpenWorkbench(connector, true) }] : []),
    ]),
  ];

  return (
    <div className="project-group">
      <ContextMenu><ContextMenuTrigger asChild><div className="project-group__header" data-active={isActive || undefined}>
        <SidebarNavRow
          className="project-group__name"
          icon={<CaretRightIcon className="project-group__chevron" data-expanded={expanded} />}
          label={<span className="project-group__identity"><ResourceIcon kind="folder" expanded={expanded} size={20} /><span>{project.name}</span></span>}
          aria-current={isActive ? "location" : undefined}
          aria-expanded={expanded}
          onClick={onSelect}
          title={project.name}
          aria-description={waitingCount ? `${waitingCount} 个对话等待审批或答复` : undefined}
          meta={waitingCount ? <span className="project-group__attention"><ThreadBeacon status="waiting_input" decorative />{waitingCount}</span> : undefined}
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
              <DotsThreeIcon size={16} aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">{actions.map(action => <DropdownMenuItem key={action.label} onSelect={action.run}>{action.icon}{action.label}</DropdownMenuItem>)}<DropdownMenuSeparator /><DropdownMenuItem onSelect={onOpenManagement}><GearIcon size={16} aria-hidden="true" />项目设置</DropdownMenuItem></DropdownMenuContent>
        </DropdownMenu>
      </div></ContextMenuTrigger><ContextMenuContent>{actions.map(action => <ContextMenuItem key={action.label} onSelect={action.run}>{action.icon}{action.label}</ContextMenuItem>)}<ContextMenuSeparator /><ContextMenuItem onSelect={onOpenManagement}><GearIcon size={16} aria-hidden="true" />项目设置</ContextMenuItem></ContextMenuContent></ContextMenu>
      {expanded ? (
        <div className="project-group__body">
          {visibleConversations.map((conversation) => (
            <SidebarNavRow
              key={conversation.id}
              icon={<ThreadBeacon status={statuses[conversation.id]} decorative />}
              label={conversationTitle(conversation.title)}
              meta={formatRelativeTime(conversation.updated_at)}
              active={conversation.id === isConversationActive}
              onClick={() => onOpenConversation(conversation.id)}
              title={`${conversation.title} · ${runPresentation(statuses[conversation.id]).label}`}
              aria-description={runPresentation(statuses[conversation.id]).label}
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
