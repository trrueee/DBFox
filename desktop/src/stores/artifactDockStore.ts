import { create } from "zustand";

import type { ResultViewArtifact } from "../types/agentArtifact";
import { useWorkspaceStore } from "./workspaceStore";

export interface ArtifactDockState {
  artifactById: Record<string, ResultViewArtifact>;
  conversationIdByArtifactId: Record<string, string>;
}

interface ArtifactDockActions {
  openArtifacts: (conversationId: string, activate?: boolean) => void;
  openArtifact: (artifact: ResultViewArtifact, conversationId?: string) => void;
}

export type ArtifactDockStore = ArtifactDockState & ArtifactDockActions;

export const useArtifactDockStore = create<ArtifactDockStore>()((set) => ({
  artifactById: {},
  conversationIdByArtifactId: {},

  openArtifacts: (conversationId, activate = true) => {
    const viewKey = `core.artifacts:${conversationId}`;
    useWorkspaceStore.getState().openDockTab(
      {
        viewKey,
        viewType: "core.artifacts",
        title: "✦ 工件",
        closeable: false,
        target: {
          type: "conversation",
          id: conversationId,
        },
      },
      activate,
    );
  },

  openArtifact: (artifact, conversationId) => {
    const viewKey = `core.artifact:${artifact.id}`;
    useWorkspaceStore.getState().openDockTab({
      viewKey,
      viewType: "core.artifact",
      title: artifact.title,
      closeable: true,
      target: {
        type: "artifact",
        id: artifact.id,
      },
    });
    set((state) => ({
      artifactById: {
        ...state.artifactById,
        [artifact.id]: artifact,
      },
      conversationIdByArtifactId: conversationId
        ? {
            ...state.conversationIdByArtifactId,
            [artifact.id]: conversationId,
          }
        : state.conversationIdByArtifactId,
    }));
  },
}));
