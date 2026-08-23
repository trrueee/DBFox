import { create } from "zustand";
import type {
  DlcContributionSet,
  DlcRegistrationRecord,
} from "./types";

export const EMPTY_CONTRIBUTIONS: DlcContributionSet = Object.freeze({
  connectors: Object.freeze([]),
  dockViews: Object.freeze([]),
  artifactRenderers: Object.freeze([]),
});

export interface DlcStoreState {
  activeSnapshotId: string | null;
  records: Record<string, DlcRegistrationRecord>;
  contributions: DlcContributionSet;
  loading: boolean;
  error: string | null;
}

export interface DlcStoreActions {
  setProjectionResult: (
    snapshotId: string,
    records: Record<string, DlcRegistrationRecord>,
    contributions: DlcContributionSet,
  ) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useDlcStore = create<DlcStoreState & DlcStoreActions>((set) => ({
  activeSnapshotId: null,
  records: {},
  contributions: EMPTY_CONTRIBUTIONS,
  loading: false,
  error: null,

  setProjectionResult: (snapshotId, records, contributions) =>
    set({
      activeSnapshotId: snapshotId,
      records,
      contributions,
      loading: false,
      error: null,
    }),

  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),
  reset: () =>
    set({
      activeSnapshotId: null,
      records: {},
      contributions: EMPTY_CONTRIBUTIONS,
      loading: false,
      error: null,
    }),
}));
