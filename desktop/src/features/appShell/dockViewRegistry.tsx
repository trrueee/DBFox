import type { ReactNode } from "react";
import { lazy } from "react";
import {
  ArtifactDockContent,
  ArtifactsDockContent,
  ConsoleDockContent,
  DockSuspense,
  TableDockContent,
  type DockShowToast,
} from "./dockViewContent";

const MultiTableWorkspace = lazy(() =>
  import("../workspace/MultiTableWorkspace").then((module) => ({ default: module.MultiTableWorkspace })),
);
const WorkspaceFileDockContent = lazy(() =>
  import("../workspace/WorkspaceFileDock").then((module) => ({ default: module.WorkspaceFileDockContent })),
);
import {
  FileText,
  GitMerge,
  Sparkles,
  Table2,
  Terminal,
} from "lucide-react";
import type { WorkspaceDockTab } from "../../types/workspace";

/**
 * Dock view contribution point.
 *
 * The Kernel only knows ordered views and their canonical keys. Each view type
 * contributes its presentation and visibility rule; adding a future view type
 * must not add another Kernel domain switch.
 */

export interface DockViewContext {
  activeProjectId: string;
  activeDatasourceId: string;
  activeConversationId: string | null;
}

export interface DockRenderContext extends DockViewContext {
  showToast: DockShowToast;
  onOpenQueryResult: (queryText: string) => void;
}

export interface DockViewContribution {
  kind: WorkspaceDockTab["kind"];
  viewType: string;
  icon: (tab: WorkspaceDockTab) => ReactNode;
  resolveTitle: (tab: WorkspaceDockTab) => string;
  isVisible: (tab: WorkspaceDockTab, context: DockViewContext) => boolean;
  render: (tab: WorkspaceDockTab, context: DockRenderContext) => ReactNode;
}

const iconProps = { size: 13, "aria-hidden": true as const };

function coreViewType(kind: string): string {
  return `core.${kind.replaceAll("-", ".")}`;
}

function dataViewType(kind: string): string {
  return `dbfox.data.${kind}`;
}

const DOCK_VIEWS: readonly DockViewContribution[] = [
  {
    kind: "console",
    viewType: "core.sql-console",
    icon: () => <Terminal {...iconProps} />,
    resolveTitle: () => "SQL 控制台",
    isVisible: (tab, context) => tab.datasourceId === context.activeDatasourceId,
    render: (tab, context) => (
      <DockSuspense>
        <ConsoleDockContent
          tab={tab}
          activeDatasourceId={context.activeDatasourceId}
          showToast={context.showToast}
        />
      </DockSuspense>
    ),
  },
  {
    kind: "table",
    viewType: dataViewType("table"),
    icon: () => <Table2 {...iconProps} />,
    resolveTitle: (tab) => tab.title,
    isVisible: (tab, context) => tab.datasourceId === context.activeDatasourceId,
    render: (tab, context) => (
      <DockSuspense>
        <TableDockContent tab={tab} showToast={context.showToast} />
      </DockSuspense>
    ),
  },
  {
    kind: "artifacts",
    viewType: coreViewType("artifacts"),
    icon: () => <Sparkles {...iconProps} />,
    resolveTitle: () => "✦ 工件",
    isVisible: (tab, context) =>
      Boolean(context.activeConversationId)
      && tab.conversationId === context.activeConversationId,
    render: (tab) => (
      <DockSuspense>
        <ArtifactsDockContent conversationId={tab.conversationId ?? ""} />
      </DockSuspense>
    ),
  },
  {
    kind: "artifact",
    viewType: coreViewType("artifact"),
    icon: () => <FileText {...iconProps} />,
    resolveTitle: (tab) => tab.title,
    isVisible: (tab, context) =>
      Boolean(context.activeConversationId)
      && tab.conversationId === context.activeConversationId,
    render: (tab, context) => (
      <DockSuspense>
        <ArtifactDockContent tab={tab} showToast={context.showToast} />
      </DockSuspense>
    ),
  },
  {
    kind: "file",
    viewType: "dbfox.workspace.file",
    icon: () => <FileText {...iconProps} />,
    resolveTitle: (tab) => tab.fileName ?? tab.title,
    isVisible: (tab, context) =>
      Boolean(tab.filePath) && (!tab.projectId || tab.projectId === context.activeProjectId),
    render: (tab) => (
      <DockSuspense>
        <WorkspaceFileDockContent tab={tab} />
      </DockSuspense>
    ),
  },
  {
    kind: "multi-table",
    viewType: dataViewType("multi-table"),
    icon: () => <GitMerge {...iconProps} />,
    resolveTitle: (tab) => tab.title,
    isVisible: () => true,
    render: (tab, context) => (
      <DockSuspense>
        <MultiTableWorkspace
          tables={tab.selectedTables ?? []}
          onOpenQueryResult={context.onOpenQueryResult}
          onToast={context.showToast}
        />
      </DockSuspense>
    ),
  },
];

const DOCK_VIEWS_BY_KIND = new Map(
  DOCK_VIEWS.map((contribution) => [contribution.kind, contribution]),
);

export function getDockView(kind: string): DockViewContribution | null {
  return DOCK_VIEWS_BY_KIND.get(kind as WorkspaceDockTab["kind"]) ?? null;
}

export function dockViewTitle(tab: WorkspaceDockTab): string {
  return getDockView(tab.kind)?.resolveTitle(tab) ?? tab.title;
}
