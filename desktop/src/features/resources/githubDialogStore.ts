import { create } from "zustand";

interface GithubDialogStore {
  open: boolean;
  projectId: string;
  openAdd: (projectId: string) => void;
  close: () => void;
}

export const useGithubDialogStore = create<GithubDialogStore>((set) => ({
  open: false,
  projectId: "",
  openAdd: (projectId) => set({ open: true, projectId }),
  close: () => set({ open: false, projectId: "" }),
}));
