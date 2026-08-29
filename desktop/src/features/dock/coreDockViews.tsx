import { FileText, Sparkles } from "lucide-react";
import {
  ArtifactDockContent,
  ArtifactsDockContent,
  DockSuspense,
} from "./dockViewContent";
import { useConversationStore } from "../../stores/conversationStore";
import type { DockViewContribution } from "./types";
import { CORE_DOCK_VIEW_TYPES } from "../dlc/coreContributionIds";

const iconProps = { size: 13, "aria-hidden": true as const };

export const coreDockViews: readonly DockViewContribution[] = [
  {
    viewType: CORE_DOCK_VIEW_TYPES.artifacts,
    icon: () => <Sparkles {...iconProps} />,
    resolveTitle: () => "✦ 工件",
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
    icon: () => <FileText {...iconProps} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => {
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
