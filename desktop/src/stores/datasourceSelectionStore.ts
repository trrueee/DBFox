import { create } from "zustand";

interface DatasourceSelectionState {
  activeDatasourceId: string;
  setActiveDatasourceId: (id: string) => void;
}

export const useDatasourceSelectionStore = create<DatasourceSelectionState>()((set) => ({
  activeDatasourceId: "",
  setActiveDatasourceId: (activeDatasourceId) => set({ activeDatasourceId }),
}));
