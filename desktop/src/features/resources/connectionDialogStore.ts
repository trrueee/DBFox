import { create } from "zustand";

interface ConnectionState {
  open: boolean;
  createMode: boolean;
  openCreate: () => void;
  openDetail: () => void;
  close: () => void;
}

export const useConnectionDialogStore = create<ConnectionState>()((set) => ({
  open: false,
  createMode: true,
  openCreate: () => set({ open: true, createMode: true }),
  openDetail: () => set({ open: true, createMode: false }),
  close: () => set({ open: false }),
}));
