import type { ConversationArtifact } from "../types/conversation";
import { useWorkspaceStore } from "./workspaceStore";

/** Dock commands only. Artifact data remains authoritative in conversationStore. */
export function openArtifactsDock(conversationId: string, activate = true): void {
    const viewKey = `core.artifacts:${conversationId}`;
    useWorkspaceStore.getState().openDockTab(
      {
        viewKey,
        viewType: "core.artifacts",
        title: "成果",
        closeable: false,
        target: {
          type: "conversation",
          id: conversationId,
        },
      },
      activate,
    );
}

export function openArtifactDock(
  artifact: Pick<ConversationArtifact, "id" | "title">,
  options: { activate?: boolean; selectedViewId?: string; projectId?: string } = {},
): void {
    const viewKey = `core.artifact:${artifact.id}`;
    useWorkspaceStore.getState().openDockTab(
      {
        viewKey,
        viewType: "core.artifact",
        title: artifact.title,
        closeable: true,
        ...(options.projectId ? { projectId: options.projectId } : {}),
        target: {
          type: "artifact",
          id: artifact.id,
        },
        selectedViewId: options.selectedViewId,
      },
      options.activate ?? true,
    );
}
