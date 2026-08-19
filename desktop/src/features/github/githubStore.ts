import { create } from "zustand";
import { githubApi } from "../../lib/api/github";
import type { GithubBindingResponse } from "../../lib/api/generated/types.gen";
import { useWorkspaceStore } from "../../stores/workspaceStore";

export interface GithubFileState {
  projectId: string;
  bindingId: string;
  revision: string;
  filePath: string;
  fileName: string;
  owner: string;
  repository: string;
}

interface GithubStoreState {
  bindingsByProject: Record<string, GithubBindingResponse[]>;
  activeBindingIdByProject: Record<string, string | null>;
  loadingByProject: Record<string, boolean>;
  errorByProject: Record<string, string | null>;
  fileStateByKey: Record<string, GithubFileState>;
}

interface GithubStoreActions {
  loadBindings: (projectId: string) => Promise<GithubBindingResponse[]>;
  addBinding: (
    projectId: string,
    repository: string,
    refName?: string,
  ) => Promise<GithubBindingResponse>;
  deleteBinding: (projectId: string, bindingId: string) => Promise<void>;
  refreshBinding: (
    projectId: string,
    bindingId: string,
  ) => Promise<GithubBindingResponse>;
  setActiveBindingId: (projectId: string, bindingId: string | null) => void;
  openGithubFile: (params: {
    projectId: string;
    bindingId: string;
    owner: string;
    repository: string;
    revision: string;
    filePath: string;
    fileName?: string;
  }) => void;
}

export type GithubStore = GithubStoreState & GithubStoreActions;

export const useGithubStore = create<GithubStore>()((set) => ({
  bindingsByProject: {},
  activeBindingIdByProject: {},
  loadingByProject: {},
  errorByProject: {},
  fileStateByKey: {},

  loadBindings: async (projectId: string) => {
    if (!projectId) return [];
    set((state) => ({
      loadingByProject: { ...state.loadingByProject, [projectId]: true },
      errorByProject: { ...state.errorByProject, [projectId]: null },
    }));
    try {
      const bindings = await githubApi.listBindings(projectId);
      set((state) => {
        const currentActive = state.activeBindingIdByProject[projectId];
        const nextActive =
          currentActive && bindings.some((b) => b.id === currentActive)
            ? currentActive
            : bindings[0]?.id ?? null;
        return {
          bindingsByProject: { ...state.bindingsByProject, [projectId]: bindings },
          activeBindingIdByProject: {
            ...state.activeBindingIdByProject,
            [projectId]: nextActive,
          },
          loadingByProject: { ...state.loadingByProject, [projectId]: false },
        };
      });
      return bindings;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      set((state) => ({
        errorByProject: { ...state.errorByProject, [projectId]: msg },
        loadingByProject: { ...state.loadingByProject, [projectId]: false },
      }));
      return [];
    }
  },

  addBinding: async (
    projectId: string,
    repository: string,
    refName: string = "main",
  ) => {
    const binding = await githubApi.createBinding(projectId, repository, refName);
    set((state) => {
      const existing = state.bindingsByProject[projectId] ?? [];
      const updated = [...existing.filter((b) => b.id !== binding.id), binding];
      return {
        bindingsByProject: { ...state.bindingsByProject, [projectId]: updated },
        activeBindingIdByProject: {
          ...state.activeBindingIdByProject,
          [projectId]: binding.id,
        },
      };
    });
    return binding;
  },

  deleteBinding: async (projectId: string, bindingId: string) => {
    await githubApi.deleteBinding(projectId, bindingId);
    set((state) => {
      const existing = state.bindingsByProject[projectId] ?? [];
      const updated = existing.filter((b) => b.id !== bindingId);
      const currentActive = state.activeBindingIdByProject[projectId];
      const nextActive =
        currentActive === bindingId ? updated[0]?.id ?? null : currentActive;
      return {
        bindingsByProject: { ...state.bindingsByProject, [projectId]: updated },
        activeBindingIdByProject: {
          ...state.activeBindingIdByProject,
          [projectId]: nextActive,
        },
      };
    });
  },

  refreshBinding: async (projectId: string, bindingId: string) => {
    const updatedBinding = await githubApi.refreshBinding(projectId, bindingId);
    set((state) => {
      const existing = state.bindingsByProject[projectId] ?? [];
      const updated = existing.map((b) =>
        b.id === bindingId ? updatedBinding : b,
      );
      return {
        bindingsByProject: { ...state.bindingsByProject, [projectId]: updated },
      };
    });
    return updatedBinding;
  },

  setActiveBindingId: (projectId: string, bindingId: string | null) => {
    set((state) => ({
      activeBindingIdByProject: {
        ...state.activeBindingIdByProject,
        [projectId]: bindingId,
      },
    }));
  },

  openGithubFile: ({
    projectId,
    bindingId,
    owner,
    repository,
    revision,
    filePath,
    fileName,
  }) => {
    const resolvedName =
      fileName?.trim()
      || filePath.split("/").filter(Boolean).at(-1)
      || filePath;
    const viewKey = `dbfox.github.file:${bindingId}:${revision}:${filePath}`;
    const stateKey = viewKey;

    useWorkspaceStore.getState().openDockTab({
      viewKey,
      viewType: "dbfox.github.file",
      title: `${resolvedName} (${owner}/${repository}@${revision.slice(0, 7)})`,
      closeable: true,
      projectId,
      target: {
        type: "resource",
        kind: "github.repository",
        id: bindingId,
      },
      stateKey,
    });

    set((state) => ({
      fileStateByKey: {
        ...state.fileStateByKey,
        [stateKey]: {
          projectId,
          bindingId,
          revision,
          filePath,
          fileName: resolvedName,
          owner,
          repository,
        },
      },
    }));
  },
}));
