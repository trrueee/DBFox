import { FileText, Sparkles } from "lucide-react";
import {
  ArtifactDockContent,
  ArtifactsDockContent,
  DockSuspense,
} from "../appShell/dockViewContent";
import { useArtifactDockStore } from "../../stores/artifactDockStore";
import type { DockViewContribution } from "./types";

const iconProps = { size: 13, "aria-hidden": true as const };

export const coreDockViews: readonly DockViewContribution[] = [
  {
    viewType: "core.artifacts",
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
    viewType: "core.artifact",
    icon: () => <FileText {...iconProps} />,
    resolveTitle: (view) => view.title,
    isVisible: (view, context) => {
      const artifactId = view.target?.type === "artifact" ? view.target.id : "";
      const convId = useArtifactDockStore.getState().conversationIdByArtifactId[artifactId];
      return (
        Boolean(context.activeConversationId)
        && (!convId || convId === context.activeConversationId)
      );
    },
    render: (view, context) => (
      <DockSuspense>
        <ArtifactDockContent tab={view} showToast={context.showToast} />
      </DockSuspense>
    ),
  },
];
