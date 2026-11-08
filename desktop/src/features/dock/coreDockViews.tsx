import {
  FileTextIcon,
  SparkleIcon,
} from "@/components/icons";
import {
  ArtifactDockContent,
  ArtifactsDockContent,
  DockSuspense,
} from "./dockViewContent";
import { useConversationStore } from "../../stores/conversationStore";
import type { DockViewContribution } from "./types";
import { CORE_DOCK_VIEW_TYPES } from "../dlc/coreContributionIds";
import { ProjectWorkbench } from "../resources/ProjectWorkbench";
import { useDlcStore } from "../dlc/extensionStore";
import { artifactKind, ResourceIcon } from "../../components/resources/resourcePresentation";
import type { WorkspaceDockTab } from "../../types/workspace";

const iconProps = { size: 16, "aria-hidden": true as const };

function ArtifactTabIcon({ view }: { view: WorkspaceDockTab }) {
  const artifactId = view.target?.type === "artifact" ? view.target.id : undefined;
  const artifact = useConversationStore(state => artifactId ? state.artifactsById[artifactId] : undefined);
  return <ResourceIcon size={16} name={artifact?.title ?? view.title}
    kind={artifact ? artifactKind(artifact.type, artifact.title) : undefined} />;
}

export const coreDockViews: readonly DockViewContribution[] = [
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
      <DockSuspense>
        <ArtifactsDockContent
          conversationId={view.target?.type === "conversation" ? view.target.id : ""}
        />
      </DockSuspense>
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
      <DockSuspense>
        <ArtifactDockContent
          key={`${view.viewKey}:${context.activeProjectId ?? ""}`}
          tab={view}
          showToast={context.showToast}
          onAsk={context.onAsk}
        />
      </DockSuspense>
    ),
  },
];
