import { create } from "zustand";
import type { RequestedResourceRef } from "../lib/api/generated/types.gen";

export const EMPTY_CONVERSATION_CONTEXT: readonly RequestedResourceRef[] = Object.freeze([]);

interface ConversationContextDraftState {
  byProject: Record<string, RequestedResourceRef[]>;
  replace(projectId: string, refs: readonly RequestedResourceRef[]): void;
  clear(projectId: string): void;
}

export const useConversationContextStore = create<ConversationContextDraftState>((set) => ({
  byProject: {},
  replace: (projectId, refs) => set((state) => ({
    byProject: { ...state.byProject, [projectId]: dedupe(refs) },
  })),
  clear: (projectId) => set((state) => {
    const byProject = { ...state.byProject };
    delete byProject[projectId];
    return { byProject };
  }),
}));

function dedupe(refs: readonly RequestedResourceRef[]): RequestedResourceRef[] {
  const seen = new Set<string>();
  return refs.filter((ref) => {
    const key = JSON.stringify([ref.kind, ref.id]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map((ref) => ({ kind: ref.kind, id: ref.id }));
}
