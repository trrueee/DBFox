import { FileText, Sparkles } from "lucide-react";
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

const iconProps = { size: 13, "aria-hidden": true as const };

export const coreDockViews: readonly DockViewContribution[] = [
  {
    viewType: CORE_DOCK_VIEW_TYPES.projectWorkbench,
    preferredWidth: 560,
    icon: (view) => useDlcStore.getState().contributions.connectors.find(item => item.id === view.stateKey)?.icon ?? <FileText {...iconProps} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => view.projectId === context.activeProjectId,
    render: (view) => <ProjectWorkbench connectorId={view.stateKey ?? ""} projectId={view.projectId ?? ""} />,
  },
  {
    viewType: CORE_DOCK_VIEW_TYPES.artifacts,
    preferredWidth: 560,
    icon: () => <Sparkles {...iconProps} />,
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
    icon: (view) => <ResourceIcon size={16} kind={artifactKind(view.target?.type === "artifact" ? useConversationStore.getState().artifactsById[view.target.id]?.type ?? "" : "")} />,
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
          tab={view}
          showToast={context.showToast}
          onAsk={context.onAsk}
        />
      </DockSuspense>
    ),
  },
];
