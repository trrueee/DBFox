import { create } from "zustand";

import type { ResultViewArtifact } from "../types/agentArtifact";
import { useWorkspaceStore } from "./workspaceStore";

interface ArtifactDockActions {
  openArtifacts: (conversationId: string, activate?: boolean) => void;
  openArtifact: (artifact: ResultViewArtifact, conversationId?: string) => void;
}

export type ArtifactDockStore = ArtifactDockActions;

export const useArtifactDockStore = create<ArtifactDockStore>()(() => ({
  openArtifacts: (conversationId, activate = true) => {
    useWorkspaceStore.getState().openDockTab(
      {
        id: `artifacts-${conversationId}`,
        kind: "artifacts",
        title: "工件",
        closeable: false,
        conversationId,
      },
      activate,
    );
  },

  openArtifact: (artifact, conversationId) => {
    useWorkspaceStore.getState().openDockTab({
      id: `artifact-${artifact.id}`,
      kind: "artifact",
      title: artifact.title,
      closeable: true,
      conversationId,
      artifact,
    });
  },
}));
