import { create } from "zustand";
import {
  admitConversationInput,
  cancelConversationRun,
  createConversation,
  deleteConversation,
  getConversation,
  getConversationHistory,
  getConversationRunArtifacts,
  listConversations,
  patchConversation,
  resolveConversationApproval,
  resolveConversationQuestion,
  selectConversationArtifact,
} from "../features/conversation/conversationRepository";
import {
  conversationStreamRuntime,
} from "../features/conversation/conversationStreamRuntime";
import {
  isFollowableRun,
  isTerminalRunItem,
} from "../features/conversation/conversationState";
import { mergeProjectionById } from "./conversationProjection";
import {
  buildConversationLlmPayload,
  getStoredApiConfig,
  type ConversationLlmPayload,
} from "../lib/llmConfig";
import { getUserErrorMessage } from "../lib/api/client";
import type {
  ApprovalItem,
  ConversationArtifact,
  ConversationDeliveryMode,
  ConversationDetail,
  ConversationRun,
  ConversationRunItem,
  ConversationStreamEvent,
  ConversationSummary,
  QuestionItem,
} from "../types/conversation";
import type { RequestedResourceRef } from "../lib/api/generated/types.gen";
import type { WorkbenchReference } from "../../../sdk/frontend/index";
import {
  reduceStreamEvent,
  removeConversationState,
  upsertArtifacts,
  upsertRun,
} from "./conversationStoreReducer";

export interface ConversationState {
  summaries: ConversationSummary[];
  activeConversationId: string | null;
  detailById: Record<string, ConversationDetail>;
  artifactsById: Record<string, ConversationArtifact>;
  liveFieldsById: Record<string, { revision: number; offset: number }>;
  streamErrorById: Record<string, string | undefined>;
}

export interface ConversationActions {
  initConversations: () => Promise<void>;
  openConversation: (conversationId: string) => Promise<ConversationDetail>;
  loadOlderHistory: (conversationId: string) => Promise<boolean>;
  createAndOpenConversation: (
    question: string,
    resourceIntents?: readonly RequestedResourceRef[],
  ) => Promise<ConversationDetail>;
  setResourceIntents: (
    conversationId: string,
    resourceIntents: readonly RequestedResourceRef[],
  ) => Promise<void>;
  deleteConversationById: (conversationId: string) => Promise<void>;
  loadConversation: (detail: ConversationDetail) => void;
  loadRunArtifacts: (
    conversationId: string,
    runId: string,
    expectedArtifactIds: readonly string[],
  ) => Promise<void>;
  sendMessage: (
    conversationId: string,
    content: string,
    mode: ConversationDeliveryMode,
    idempotencyKey: string,
    requestedResources?: readonly RequestedResourceRef[],
    references?: readonly WorkbenchReference[],
  ) => Promise<void>;
  cancelRun: (runId: string) => Promise<void>;
  resolveApproval: (runId: string, approvalId: string, approved: boolean) => Promise<void>;
  resolveQuestion: (
    runId: string,
    questionId: string,
    response: { selected_value?: string; text?: string },
  ) => Promise<void>;
  selectArtifact: (conversationId: string, artifactId: string) => Promise<void>;
  applyStreamEvent: (event: ConversationStreamEvent) => void;
  applyStreamEvents: (events: ConversationStreamEvent[]) => void;
}

export type ConversationStore = ConversationState & ConversationActions;

const artifactLoadRequests = new Map<string, Promise<void>>();

export const useConversationStore = create<ConversationStore>()((set, get) => ({
  summaries: [],
  activeConversationId: null,
  detailById: {},
  artifactsById: {},
  liveFieldsById: {},
  streamErrorById: {},

  initConversations: async () => {
    set({ summaries: await listConversations() });
  },

  openConversation: async (conversationId) => {
    const detail = await getConversation(conversationId);
    get().loadConversation(detail);
    const activeRun = detail.runs.findLast((run) => isFollowableRun(run.status));
    if (activeRun) void followRun(get, conversationId, activeRun.id, detail.cursor || 0);
    return detail;
  },

  loadOlderHistory: async (conversationId) => {
    const current = get().detailById[conversationId];
    if (!current?.pagination) return false;
    const itemCursor = current.pagination.items.next_before_sequence;
    const runCursor = current.pagination.runs.next_before_sequence;
    if (!itemCursor && !runCursor) return false;
    const page = await getConversationHistory(conversationId, {
      beforeItemSequence: itemCursor,
      beforeRunSequence: runCursor,
    });
    get().loadConversation({
      ...current,
      items: mergeProjectionById(page.items, current.items),
      runs: mergeProjectionById(page.runs, current.runs),
      pagination: page.pagination,
      cursor: Math.max(current.cursor || 0, page.cursor || 0),
    });
    return Boolean(page.pagination?.items.has_more || page.pagination?.runs.has_more);
  },

  createAndOpenConversation: async (question, resourceIntents = []) => {
    requireConversationLlmPayload();
    const { useWorkspaceStore } = await import("../stores/workspaceStore");
    const projectId = useWorkspaceStore.getState().activeProjectId;
    if (!projectId) throw new Error("Please select a project first.");
    const detail = await createConversation({
      project_id: projectId,
      title: question.slice(0, 80),
      resource_intents: [...resourceIntents],
    });
    const summary: ConversationSummary = {
      id: detail.id,
      title: detail.title,
      project_id: detail.project_id ?? projectId,
      updated_at: new Date().toISOString(),
    };
    set((state) => ({
      summaries: [summary, ...state.summaries.filter((item) => item.id !== summary.id)],
    }));
    get().loadConversation(detail);
    return detail;
  },

  setResourceIntents: async (conversationId, resourceIntents) => {
    const detail = await patchConversation(conversationId, {
      resource_intents: [...resourceIntents],
    });
    get().loadConversation(detail);
  },

  deleteConversationById: async (conversationId) => {
    conversationStreamRuntime.stop(conversationId);
    await deleteConversation(conversationId);
    set((state) => removeConversationState(state, conversationId));
  },

  loadConversation: (detail) => {
    const terminalItemIds = new Set(
      detail.items
        .filter((item) => isTerminalRunItem(item.status))
        .map((item) => item.id),
    );
    set((state) => ({
      activeConversationId: detail.id,
      detailById: {
        ...state.detailById,
        [detail.id]: preserveLiveProjection(
          state.detailById[detail.id],
          detail,
          state.liveFieldsById,
        ),
      },
      liveFieldsById: Object.fromEntries(
        Object.entries(state.liveFieldsById)
          .filter(([key]) => ![...terminalItemIds].some((itemId) => key.includes(`:${itemId}:`))),
      ),
    }));
  },

  loadRunArtifacts: async (conversationId, runId, expectedArtifactIds) => {
    const artifactIds = [...new Set(expectedArtifactIds)];
    if (artifactIds.length === 0) return;
    if (artifactIds.every((artifactId) => Boolean(get().artifactsById[artifactId]))) return;

    const requestKey = `${conversationId}:${runId}`;
    const activeRequest = artifactLoadRequests.get(requestKey);
    if (activeRequest) await activeRequest;
    if (artifactIds.every((artifactId) => Boolean(get().artifactsById[artifactId]))) return;

    const request = (async () => {
      const artifacts = await getConversationRunArtifacts(conversationId, runId);
      set((state) => upsertArtifacts(state, artifacts));
    })();
    artifactLoadRequests.set(requestKey, request);
    try {
      await request;
    } finally {
      if (artifactLoadRequests.get(requestKey) === request) {
        artifactLoadRequests.delete(requestKey);
      }
    }
  },

  sendMessage: async (
    conversationId,
    content,
    mode,
    idempotencyKey,
    requestedResources = [],
    references = [],
  ) => {
    const llmPayload = requireConversationLlmPayload();
    const detail = get().detailById[conversationId]
      || await get().openConversation(conversationId);
    const created = await admitConversationInput(conversationId, {
      content,
      idempotency_key: idempotencyKey,
      delivery_mode: mode,
      ...(requestedResources.length > 0 ? {
        requested_resources: requestedResources.map((ref) => ({
          kind: ref.kind,
          id: ref.id,
        })),
      } : {}),
      ...(references.length > 0 ? {
        references: references.map((reference) => ({
          label: reference.label,
          authority: reference.authority
            ? { kind: reference.authority.kind, id: reference.authority.id }
            : null,
          object: reference.object
            ? {
                kind: reference.object.kind,
                id: reference.object.id,
                version: reference.object.version ?? null,
              }
            : null,
          locator: reference.locator ?? null,
          artifact_id: reference.artifactId ?? null,
        })),
      } : {}),
      selected_artifact_ids: detail.selected_artifact_id ? [detail.selected_artifact_id] : [],
      llm_credential_id: llmPayload.llm_credential_id,
      api_base: llmPayload.api_base,
      model_name: llmPayload.model_name,
      workspace_context: {
        recent_agent_run_id: detail.runs.at(-1)?.id || null,
      },
    });
    get().loadConversation({
      ...detail,
      items: mergeProjectionById(detail.items, created.projection.items),
      runs: mergeProjectionById(detail.runs, created.projection.runs),
      cursor: Math.max(detail.cursor || 0, created.event_cursor, created.projection.cursor),
    });
    void followRun(get, conversationId, created.run_id, created.projection.cursor);
  },

  cancelRun: async (runId) => {
    const run = findRun(get(), runId);
    if (!run) return;
    const cancelled = await cancelConversationRun(runId);
    set((state) => upsertRun(state, run.session_id, {
      ...run,
      status: cancelled.status as ConversationRun["status"],
      version: cancelled.version,
      cancel_requested: true,
    }));
    conversationStreamRuntime.stop(run.session_id);
    const snapshot = await getConversation(run.session_id);
    get().loadConversation(snapshot);
    const current = snapshot.runs.find((item) => item.id === runId);
    if (current && isFollowableRun(current.status)) {
      void followRun(get, run.session_id, runId, snapshot.cursor || 0);
    }
  },

  resolveApproval: async (runId, approvalId, approved) => {
    const run = findRun(get(), runId);
    const approval = findItem<ApprovalItem>(get(), approvalId, "approval");
    if (!run || !approval) return;
    const afterSequence = get().detailById[run.session_id]?.cursor || 0;
    await resolveConversationApproval(
      approvalId,
      approval.payload.version,
      approved,
      approved ? "用户允许本次操作" : "用户拒绝本次操作",
    );
    void followRun(get, run.session_id, runId, afterSequence);
  },

  resolveQuestion: async (runId, questionId, response) => {
    const run = findRun(get(), runId);
    const question = findItem<QuestionItem>(get(), questionId, "question");
    if (!run || !question) return;
    const afterSequence = get().detailById[run.session_id]?.cursor || 0;
    await resolveConversationQuestion(questionId, question.payload.version, response);
    void followRun(get, run.session_id, runId, afterSequence);
  },

  selectArtifact: async (conversationId, artifactId) => {
    await selectConversationArtifact(conversationId, artifactId);
    set((state) => {
      const detail = state.detailById[conversationId];
      return detail
        ? {
            detailById: {
              ...state.detailById,
              [conversationId]: { ...detail, selected_artifact_id: artifactId },
            },
          }
        : state;
    });
  },

  applyStreamEvent: (event) => set((state) => reduceStreamEvent(state, event)),
  applyStreamEvents: (events) => {
    if (events.length > 0) set((state) => events.reduce(reduceStreamEvent, state));
  },
}));

async function followRun(
  get: () => ConversationStore,
  conversationId: string,
  runId: string,
  afterSequence: number,
): Promise<void> {
  useConversationStore.setState((state) => ({
    streamErrorById: { ...state.streamErrorById, [conversationId]: undefined },
  }));
  await conversationStreamRuntime.follow(conversationId, runId, afterSequence, {
    applyEvents: (events) => get().applyStreamEvents(events),
    loadSnapshot: (snapshot) => get().loadConversation(snapshot),
    onError: (error) => useConversationStore.setState((state) => ({
      streamErrorById: {
        ...state.streamErrorById,
        [conversationId]: getUserErrorMessage(
          error,
          "智能分析连接异常，请刷新后重试。",
        ),
      },
    })),
  });
}

function requireConversationLlmPayload(): ConversationLlmPayload & { llm_credential_id: string } {
  const payload = buildConversationLlmPayload(getStoredApiConfig());
  if (!payload.llm_credential_id) {
    throw new Error("请先配置模型后再开始智能分析。");
  }
  return payload as ConversationLlmPayload & { llm_credential_id: string };
}

function findItem<T extends ConversationRunItem>(
  state: ConversationStore,
  itemId: string,
  type: T["type"],
): T | null {
  const item = Object.values(state.detailById)
    .flatMap((detail) => detail.items)
    .find((candidate) => candidate.id === itemId);
  return item?.type === type ? item as T : null;
}

function findRun(state: ConversationStore, runId: string): ConversationRun | null {
  return Object.values(state.detailById)
    .flatMap((detail) => detail.runs)
    .find((run) => run.id === runId) ?? null;
}

function preserveLiveProjection(
  current: ConversationDetail | undefined,
  snapshot: ConversationDetail,
  liveFields: ConversationState["liveFieldsById"],
): ConversationDetail {
  if (!current) return snapshot;
  const currentItems = new Map(current.items.map((item) => [item.id, item]));
  const items = mergeProjectionById(current.items, snapshot.items).sort(
    (left, right) => left.sequence - right.sequence
      || left.created_at.localeCompare(right.created_at)
      || left.id.localeCompare(right.id),
  );
  return {
    ...snapshot,
    runs: mergeProjectionById(current.runs, snapshot.runs).sort(
      (left, right) => left.session_sequence - right.session_sequence,
    ),
    items: items.map((item) => {
      if (item.type !== "message" || isTerminalRunItem(item.status)) {
        return item;
      }
      const fieldKey = `${item.run_id}:${item.id}:content`;
      const liveItem = currentItems.get(item.id);
      return liveFields[fieldKey] && liveItem?.type === "message"
        ? {
            ...item,
            payload: { ...item.payload, content: liveItem.payload.content },
          }
        : item;
    }),
    pagination: (
      current.items.length > snapshot.items.length
      || current.runs.length > snapshot.runs.length
    )
      ? current.pagination
      : snapshot.pagination,
  };
}
