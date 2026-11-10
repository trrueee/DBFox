import { lazy, Suspense } from "react";
import {
  FileTextIcon,
  SparkleIcon,
  TerminalWindowIcon,
} from "@/components/icons";
import { LoadingState } from "../../components/ui";
import { useConversationStore } from "../../stores/conversationStore";
import type { DockViewContribution } from "./types";
import { CORE_DOCK_VIEW_TYPES } from "../dlc/coreContributionIds";
import { ProjectWorkbench } from "../resources/ProjectWorkbench";
import { useDlcStore } from "../dlc/extensionStore";
import { artifactKind, ResourceIcon } from "../../components/resources/resourcePresentation";
import type { WorkspaceDockTab } from "../../types/workspace";

const iconProps = { size: 16, "aria-hidden": true as const };
const ArtifactDockContent = lazy(() =>
  import("./dockViewContent").then((module) => ({ default: module.ArtifactDockContent })),
);
const ArtifactsDockContent = lazy(() =>
  import("./dockViewContent").then((module) => ({ default: module.ArtifactsDockContent })),
);
const ExecutionJobsDock = lazy(() =>
  import("./ExecutionJobsDock").then((module) => ({ default: module.ExecutionJobsDock })),
);

function ArtifactTabIcon({ view }: { view: WorkspaceDockTab }) {
  const artifactId = view.target?.type === "artifact" ? view.target.id : undefined;
  const artifact = useConversationStore(state => artifactId ? state.artifactsById[artifactId] : undefined);
  return <ResourceIcon size={16} name={artifact?.title ?? view.title}
    kind={artifact ? artifactKind(artifact.type, artifact.title) : undefined} />;
}

export const coreDockViews: readonly DockViewContribution[] = [
  {
    viewType: CORE_DOCK_VIEW_TYPES.execution,
    preferredWidth: 430,
    icon: () => <TerminalWindowIcon {...iconProps} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => view.target?.type === "conversation" && view.target.id === context.activeConversationId,
    render: (view) => (
      <Suspense fallback={<LoadingState label="正在载入运行输出" />}>
        <ExecutionJobsDock key={view.viewKey} conversationId={view.sessionId ?? ""} jobId={view.stateKey} />
      </Suspense>
    ),
  },
  {
    viewType: CORE_DOCK_VIEW_TYPES.projectWorkbench,
    preferredWidth: 560,
    icon: (view) => useDlcStore.getState().contributions.connectors.find(item => item.id === view.stateKey)?.icon ?? <FileTextIcon {...iconProps} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => view.projectId === context.activeProjectId,
    render: (view) => <ProjectWorkbench connectorId={view.stateKey ?? ""} projectId={view.projectId ?? ""} />,
  },
  {
    viewType: CORE_DOCK_VIEW_TYPES.artifacts,
    preferredWidth: 560,
    icon: () => <SparkleIcon {...iconProps} />,
    resolveTitle: () => "成果",
    isVisible: (view, context) =>
      Boolean(context.activeConversationId)
      && view.target?.type === "conversation"
      && view.target.id === context.activeConversationId,
    render: (view) => (
      <Suspense fallback={<LoadingState label="正在载入工作台" />}>
        <ArtifactsDockContent
          conversationId={view.target?.type === "conversation" ? view.target.id : ""}
        />
      </Suspense>
    ),
  },
  {
    viewType: CORE_DOCK_VIEW_TYPES.artifact,
    preferredWidth: 600,
    icon: (view) => <ArtifactTabIcon view={view} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => {
      if (view.target?.type !== "artifact") return false;
      // Explicit Host navigation verifies the artifact's Project before adding
      // this existing tab metadata. Action Runs need not be the active chat.
      if (view.projectId) return view.projectId === context.activeProjectId;
      const artifactId = view.target?.type === "artifact" ? view.target.id : "";
      const convId = useConversationStore.getState().artifactsById[artifactId]?.session_id;
      return (
        Boolean(context.activeConversationId)
        && (!convId || convId === context.activeConversationId)
      );
    },
    render: (view, context) => (
      <Suspense fallback={<LoadingState label="正在载入工作台" />}>
        <ArtifactDockContent
          key={`${view.viewKey}:${context.activeProjectId ?? ""}`}
          tab={view}
          showToast={context.showToast}
          onAsk={context.onAsk}
        />
      </Suspense>
    ),
  },
];
