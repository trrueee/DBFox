import { create } from "zustand";

import { useWorkspaceStore } from "./workspaceStore";

export interface WorkspaceFileState {
  projectId?: string;
  filePath: string;
  fileName: string;
}

interface WorkspaceFileStoreState {
  fileStateByKey: Record<string, WorkspaceFileState>;
}

interface WorkspaceFileActions {
  openFile: (filePath: string, fileName?: string, projectId?: string) => void;
}

export type WorkspaceFileStore = WorkspaceFileStoreState & WorkspaceFileActions;

export const useWorkspaceFileStore = create<WorkspaceFileStore>()((set) => ({
  fileStateByKey: {},

  openFile: (filePath, fileName, projectId) => {
    const resolvedName =
      fileName?.trim()
      || filePath.split("\\").flatMap((part) => part.split("/")).filter(Boolean).at(-1)
      || filePath;
    const viewKey = `dbfox.workspace.file:${projectId || "workspace"}:${filePath}`;
    const stateKey = viewKey;

    useWorkspaceStore.getState().openDockTab({
      viewKey,
      viewType: "dbfox.workspace.file",
      title: resolvedName,
      closeable: true,
      projectId,
      target: {
        type: "resource",
        kind: "workspace",
        id: projectId || "workspace",
      },
      stateKey,
    });

    set((state) => ({
      fileStateByKey: {
        ...state.fileStateByKey,
        [stateKey]: {
          projectId,
          filePath,
          fileName: resolvedName,
        },
      },
    }));
  },
}));
