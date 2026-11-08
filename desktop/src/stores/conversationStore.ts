import { create } from "zustand";
import {
  admitConversationInput,
  cancelConversationRun,
  createConversation,
  deleteConversation,
  getConversation,
  getConversationHistory,
  getConversationRunArtifacts,
  getProjectArtifact,
  listConversations,
  patchConversation,
  resolveConversationApproval,
  resolveConversationQuestion,
  selectConversationArtifact,
} from "../features/conversation/conversationRepository";
import {
  conversationStreamRuntime,
  type ConversationStreamState,
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
import type { WorkbenchReference } from "../types/workspace";
import {
  reduceStreamEvent,
  removeConversationState,
  upsertArtifacts,
  upsertRun,
} from "./conversationStoreReducer";
import { useWorkspaceStore } from "./workspaceStore";
import { conversationTitle } from "../features/conversation/conversationTitle";

export interface ConversationState {
  summaries: ConversationSummary[];
  detailById: Record<string, ConversationDetail>;
  artifactsById: Record<string, ConversationArtifact>;
  liveFieldsById: Record<string, { revision: number; offset: number }>;
  streamErrorById: Record<string, string | undefined>;
  streamStateById: Record<string, ConversationStreamState | undefined>;
}

export interface ConversationActions {
  initConversations: () => Promise<void>;
  openConversation: (conversationId: string) => Promise<ConversationDetail>;
  loadOlderHistory: (conversationId: string) => Promise<boolean>;
  createAndOpenConversation: (question: string) => Promise<ConversationDetail>;
  deleteConversationById: (conversationId: string) => Promise<void>;
  renameConversation: (conversationId: string, title: string) => Promise<void>;
  loadConversation: (detail: ConversationDetail) => void;
  loadArtifact: (
    projectId: string,
    artifactId: string,
    options: { signal: AbortSignal; beforeCommit: () => void },
  ) => Promise<void>;
  loadRunArtifacts: (
    conversationId: string,
    runId: string,
    expectedArtifactIds: readonly string[],
    /** A navigation read is fresh and independent of shared timeline requests. */
    options?: {
      signal?: AbortSignal;
      beforeCommit: () => void;
      afterCommit: () => void;
    },
  ) => Promise<void>;
  sendMessage: (
    conversationId: string,
    content: string,
    mode: ConversationDeliveryMode,
    idempotencyKey: string,
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
  detailById: {},
  artifactsById: {},
  liveFieldsById: {},
  streamErrorById: {},
  streamStateById: {},

  initConversations: async () => {
    set({ summaries: await listConversations() });
  },

  openConversation: async (conversationId) => {
    const detail = await getConversation(conversationId);
    get().loadConversation(detail);
    const current = get().detailById[conversationId];
    const activeRun = current.runs.findLast((run) => isFollowableRun(run.status));
    if (activeRun) {
      void followRun(get, conversationId, activeRun.id, current.cursor || 0);
    } else {
      set((state) => ({
        streamErrorById: { ...state.streamErrorById, [conversationId]: undefined },
        streamStateById: { ...state.streamStateById, [conversationId]: "idle" },
      }));
    }
    return current;
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
    const latest = get().detailById[conversationId];
    if (!latest) return false;
    get().loadConversation({
      ...latest,
      items: mergeProjectionById(page.items, latest.items, item => item.revision),
      runs: mergeProjectionById(page.runs, latest.runs, run => run.version),
      pagination: page.pagination,
      cursor: Math.max(latest.cursor || 0, page.cursor || 0),
    });
    return Boolean(page.pagination?.items.has_more || page.pagination?.runs.has_more);
  },

  createAndOpenConversation: async (question) => {
    // A local draft/preview can exist before model configuration. Send owns
    // credential validation and no Agent Run starts here.
    const projectId = useWorkspaceStore.getState().activeProjectId;
    if (!projectId) throw new Error("Please select a project first.");
    const detail = await createConversation({
      project_id: projectId,
      title: conversationTitle(question),
      resource_intents: [],
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

  renameConversation: async (conversationId, title) => {
    const detail = await patchConversation(conversationId, { title: title.trim() });
    set(state => ({
      summaries: state.summaries.map(item => item.id === conversationId ? { ...item, title: detail.title } : item),
      detailById: state.detailById[conversationId] ? {
        ...state.detailById, [conversationId]: { ...state.detailById[conversationId], title: detail.title },
      } : state.detailById,
    }));
  },

  deleteConversationById: async (conversationId) => {
    conversationStreamRuntime.stop(conversationId);
    await deleteConversation(conversationId);
    set((state) => removeConversationState(state, conversationId));
    const workspace = useWorkspaceStore.getState();
    const surface = workspace.activeProjectId
      ? workspace.mainSurfaceByProject[workspace.activeProjectId]
      : undefined;
    if (surface?.kind === "conversation" && surface.conversationId === conversationId) {
      workspace.showSmartQueryHome();
    }
  },

  loadConversation: (detail) => {
    const terminalItemIds = new Set(
      detail.items
        .filter((item) => isTerminalRunItem(item.status))
        .map((item) => item.id),
    );
    set((state) => ({
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

  loadArtifact: async (projectId, artifactId, options) => {
    const artifact = await getProjectArtifact(projectId, artifactId, options.signal);
    options.signal.throwIfAborted();
    const cached = get().artifactsById[artifactId];
    if (artifact.id !== artifactId || (cached && (
      cached.session_id !== artifact.session_id || cached.run_id !== artifact.run_id
    ))) {
      throw new Error("Artifact identity conflicts with the requested projection.");
    }
    options.beforeCommit();
    set((state) => upsertArtifacts(state, [artifact]));
  },

  loadRunArtifacts: async (conversationId, runId, expectedArtifactIds, options) => {
    const artifactIds = [...new Set(expectedArtifactIds)];
    if (artifactIds.length === 0) return;
    const isLoaded = () => artifactIds.every((artifactId) => {
      const artifact = get().artifactsById[artifactId];
      return artifact?.session_id === conversationId && artifact.run_id === runId;
    });

    const load = async () => {
      options?.signal?.throwIfAborted();
      const artifacts = await getConversationRunArtifacts(conversationId, runId, options?.signal);
      options?.signal?.throwIfAborted();
      const ids = new Set(artifacts.map((artifact) => artifact.id));
      if (ids.size !== artifacts.length || artifacts.some((artifact) => (
        artifact.session_id !== conversationId || artifact.run_id !== runId
      )) || (options && artifactIds.some((id) => !ids.has(id)))) {
        throw new Error("Artifact response does not match the requested run.");
      }
      if (artifacts.some((artifact) => {
        const cached = get().artifactsById[artifact.id];
        return cached && (cached.session_id !== conversationId || cached.run_id !== runId);
      })) {
        throw new Error("Artifact identity conflicts with the existing projection.");
      }
      options?.beforeCommit();
      set((state) => upsertArtifacts(state, artifacts));
      options?.afterCommit();
    };
    // A caller's cancellation or activation must not affect another consumer.
    if (options) return load();
    if (isLoaded()) return;

    const requestKey = `${conversationId}:${runId}`;
    const activeRequest = artifactLoadRequests.get(requestKey);
    if (activeRequest) await activeRequest;
    if (isLoaded()) return;

    const request = load();
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
    references = [],
  ) => {
    const llmPayload = requireConversationLlmPayload();
    const detail = get().detailById[conversationId]
      || await get().openConversation(conversationId);
    const created = await admitConversationInput(conversationId, {
      content,
      idempotency_key: idempotencyKey,
      delivery_mode: mode,
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
    const latest = get().detailById[conversationId];
    if (!latest) return;
    get().loadConversation({
      ...latest,
      items: mergeProjectionById(latest.items, created.projection.items, item => item.revision),
      runs: mergeProjectionById(latest.runs, created.projection.runs, run => run.version),
      cursor: Math.max(latest.cursor || 0, created.event_cursor, created.projection.cursor),
    });
    void followRun(get, conversationId, created.run_id, get().detailById[conversationId].cursor || 0);
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
    await get().openConversation(run.session_id);
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
    onConnectionState: (connectionState) => useConversationStore.setState((state) => ({
      streamStateById: {
        ...state.streamStateById,
        [conversationId]: connectionState,
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
  const items = mergeProjectionById(current.items, snapshot.items, item => item.revision).sort(
    (left, right) => left.sequence - right.sequence
      || left.created_at.localeCompare(right.created_at)
      || left.id.localeCompare(right.id),
  );
  return {
    ...((snapshot.cursor || 0) < (current.cursor || 0) ? current : snapshot),
    cursor: Math.max(current.cursor || 0, snapshot.cursor || 0),
    runs: mergeProjectionById(current.runs, snapshot.runs, run => run.version).sort(
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
