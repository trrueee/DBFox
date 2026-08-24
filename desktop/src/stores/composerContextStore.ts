import { create } from "zustand";
import type { RequestedResourceRef } from "../lib/api/generated/types.gen";

export const EMPTY_COMPOSER_CONTEXT: readonly RequestedResourceRef[] = Object.freeze([]);

interface ComposerContextState {
  byConversation: Record<string, RequestedResourceRef[]>;
  replace(conversationId: string, refs: readonly RequestedResourceRef[]): void;
  add(conversationId: string, ref: RequestedResourceRef): void;
  remove(conversationId: string, ref: RequestedResourceRef): void;
  clear(conversationId: string): void;
}

export const useComposerContextStore = create<ComposerContextState>((set) => ({
  byConversation: {},
  replace: (conversationId, refs) => set((state) => ({
    byConversation: {
      ...state.byConversation,
      [conversationId]: dedupe(refs),
    },
  })),
  add: (conversationId, ref) => set((state) => ({
    byConversation: {
      ...state.byConversation,
      [conversationId]: dedupe([
        ...(state.byConversation[conversationId] ?? []),
        ref,
      ]),
    },
  })),
  remove: (conversationId, ref) => set((state) => ({
    byConversation: {
      ...state.byConversation,
      [conversationId]: (state.byConversation[conversationId] ?? []).filter(
        (candidate) => resourceKey(candidate) !== resourceKey(ref),
      ),
    },
  })),
  clear: (conversationId) => set((state) => {
    const byConversation = { ...state.byConversation };
    delete byConversation[conversationId];
    return { byConversation };
  }),
}));

function dedupe(refs: readonly RequestedResourceRef[]): RequestedResourceRef[] {
  const seen = new Set<string>();
  const result: RequestedResourceRef[] = [];
  for (const ref of refs) {
    const key = resourceKey(ref);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({ kind: ref.kind, id: ref.id });
  }
  return result;
}

function resourceKey(ref: Pick<RequestedResourceRef, "kind" | "id">): string {
  return JSON.stringify([ref.kind, ref.id]);
}
