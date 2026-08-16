import { create } from "zustand";

import { useWorkspaceStore } from "./workspaceStore";

interface WorkspaceFileActions {
  openFile: (filePath: string, fileName?: string, projectId?: string) => void;
}

export type WorkspaceFileStore = WorkspaceFileActions;

export const useWorkspaceFileStore = create<WorkspaceFileStore>()(() => ({
  openFile: (filePath, fileName, projectId) => {
    const resolvedName =
      fileName?.trim()
      || filePath.split("\\").flatMap((part) => part.split("/")).filter(Boolean).at(-1)
      || filePath;
    useWorkspaceStore.getState().openDockTab({
      id: `file-${projectId || "workspace"}-${filePath}`,
      kind: "file",
      title: resolvedName,
      closeable: true,
      projectId,
      filePath,
      fileName: resolvedName,
    });
  },
}));
