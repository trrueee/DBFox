import { create } from "zustand";
import {
  admitConversationInput,
  cancelConversationRun,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  resolveConversationApproval,
  resolveConversationQuestion,
  selectConversationArtifact,
  streamConversation,
} from "../features/conversation/conversationRepository";
import { createStreamEventBatcher } from "../features/conversation/streamEventBatcher";
import { buildConversationLlmPayload, getStoredApiConfig } from "../lib/llmConfig";
import type {
  ConversationArtifact,
  ConversationDetail,
  ConversationMessage,
  ConversationRun,
  ConversationStreamEvent,
  ConversationSummary,
  ConversationDeliveryMode,
} from "../types/conversation";
import { useDatasourceStore } from "./datasourceStore";
import {
  reduceStreamEvent,
  upsertRun,
} from "./conversationStoreReducer";

export interface ConversationState {
  summaries: ConversationSummary[];
  activeConversationId: string | null;
  detailById: Record<string, ConversationDetail>;
  messagesById: Record<string, ConversationMessage>;
  runsById: Record<string, ConversationRun>;
  artifactsById: Record<string, ConversationArtifact>;
  liveRevisionById: Record<string, number>;
  abortControllers: Map<string, AbortController>;
}

export interface ConversationActions {
  initConversations: () => Promise<void>;
  openConversation: (conversationId: string) => Promise<ConversationDetail>;
  createAndOpenConversation: (question: string, contextTables: string[]) => Promise<ConversationDetail>;
  deleteConversationById: (conversationId: string) => Promise<void>;
  loadConversation: (detail: ConversationDetail) => void;
  sendMessage: (conversationId: string, content: string, mode?: ConversationDeliveryMode) => Promise<void>;
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

export const useConversationStore = create<ConversationStore>()((set, get) => ({
  summaries: [],
  activeConversationId: null,
  detailById: {},
  messagesById: {},
  runsById: {},
  artifactsById: {},
  liveRevisionById: {},
  abortControllers: new Map(),

  initConversations: async () => {
    const summaries = await listConversations();
    set({ summaries });
  },

  openConversation: async (conversationId) => {
    const detail = await getConversation(conversationId);
    get().loadConversation(detail);
    const activeRun = detail.runs.findLast((run) => isFollowableRun(run.status));
    if (activeRun) {
      void followRun(get, conversationId, activeRun.id, detail.cursor || 0);
    }
    return detail;
  },

  createAndOpenConversation: async (question, contextTables) => {
    const datasourceId = useDatasourceStore.getState().activeDatasourceId;
    if (!datasourceId) throw new Error("Please select a datasource first.");
    const detail = await createConversation({
      datasource_id: datasourceId,
      title: question.slice(0, 80),
      context_tables: contextTables,
    });
    get().loadConversation(detail);
    return detail;
  },

  deleteConversationById: async (conversationId) => {
    await deleteConversation(conversationId);
    set((state) => ({
      summaries: state.summaries.filter((item) => item.id !== conversationId),
      activeConversationId: state.activeConversationId === conversationId ? null : state.activeConversationId,
    }));
  },

  loadConversation: (detail) => {
    const current = get();
    const messagesById = { ...current.messagesById };
    const runsById = { ...current.runsById };
    const artifactsById = { ...current.artifactsById };
    const runs = detail.runs;
    const loadedDetail = { ...detail, runs };
    for (const message of loadedDetail.messages) messagesById[message.id] = message;
    for (const run of loadedDetail.runs) runsById[run.id] = run;
    for (const artifact of loadedDetail.artifacts) artifactsById[artifact.id] = artifact;
    const livePrefix = `live:${loadedDetail.id}:`;
    const liveRevisionById = Object.fromEntries(
      Object.entries(current.liveRevisionById).filter(([id]) => !id.startsWith(livePrefix)),
    );
    set((state) => ({
      activeConversationId: loadedDetail.id,
      detailById: { ...state.detailById, [loadedDetail.id]: loadedDetail },
      messagesById,
      runsById,
      artifactsById,
      liveRevisionById,
    }));
  },

  sendMessage: async (conversationId, content, mode = "queue") => {
    const llmPayload = buildConversationLlmPayload(getStoredApiConfig());
    if (!llmPayload.llm_credential_id) throw new Error("请先配置模型后再开始智能分析。");
    const detail = get().detailById[conversationId] || await get().openConversation(conversationId);
    const created = await admitConversationInput(conversationId, {
      content,
      idempotency_key: globalThis.crypto?.randomUUID?.() || `input-${Date.now()}-${Math.random()}`,
      delivery_mode: mode,
      selected_artifact_ids: detail.selected_artifact_id ? [detail.selected_artifact_id] : [],
      llm_credential_id: llmPayload.llm_credential_id,
      api_base: llmPayload.api_base,
      model_name: llmPayload.model_name,
      workspace_context: {
        datasource_id: detail.datasource_id,
        selected_table_names: detail.context_tables,
        recent_agent_run_id: detail.runs.at(-1)?.id || null,
      },
    });
    const admittedSnapshot = await getConversation(conversationId);
    get().loadConversation(admittedSnapshot);
    await followRun(get, conversationId, created.run_id, admittedSnapshot.cursor || 0);
  },

  cancelRun: async (runId) => {
    const run = get().runsById[runId];
    try {
      const cancelled = await cancelConversationRun(runId);
      if (run) {
        set((state) => upsertRun(state, run.conversation_id, {
          ...run,
          status: cancelled.status as ConversationRun["status"],
          version: cancelled.version,
          cancel_requested: true,
        }));
      }
    } catch {
      return;
    }
    if (run) {
      get().abortControllers.get(run.conversation_id)?.abort();
      const snapshot = await getConversation(run.conversation_id);
      get().loadConversation(snapshot);
      const current = snapshot.runs.find((item) => item.id === runId);
      if (current && isFollowableRun(current.status)) {
        await followRun(get, run.conversation_id, runId, snapshot.cursor || 0);
      }
    }
  },

  resolveApproval: async (runId, approvalId, approved) => {
    const run = get().runsById[runId];
    if (!run?.approval) return;
    await resolveConversationApproval(
      approvalId,
      run.approval.version || 0,
      approved,
      approved ? "用户允许本次操作" : "用户拒绝本次操作",
    );
    const snapshot = await getConversation(run.conversation_id);
    get().loadConversation(snapshot);
    await followRun(get, run.conversation_id, runId, snapshot.cursor || 0);
  },

  resolveQuestion: async (runId, questionId, response) => {
    const run = get().runsById[runId];
    if (!run) return;
    const detail = get().detailById[run.conversation_id];
    const question = detail?.questions?.find((item) => item.id === questionId);
    if (!question) return;
    await resolveConversationQuestion(questionId, question.version, response);
    const snapshot = await getConversation(run.conversation_id);
    get().loadConversation(snapshot);
    await followRun(get, run.conversation_id, runId, snapshot.cursor || 0);
  },

  selectArtifact: async (conversationId, artifactId) => {
    await selectConversationArtifact(conversationId, artifactId);
    set((state) => {
      const detail = state.detailById[conversationId];
      if (!detail) return state;
      return {
        ...state,
        detailById: {
          ...state.detailById,
          [conversationId]: { ...detail, selected_artifact_id: artifactId },
        },
      };
    });
  },

  applyStreamEvent: (event) => set((state) => reduceStreamEvent(state, event)),
  applyStreamEvents: (events) => {
    if (events.length === 0) return;
    set((state) => events.reduce(reduceStreamEvent, state));
  },
}));

async function followRun(
  get: () => ConversationStore,
  conversationId: string,
  runId: string,
  afterSequence: number,
): Promise<void> {
  get().abortControllers.get(conversationId)?.abort();
  const abortController = new AbortController();
  const batchEvent = createStreamEventBatcher<ConversationStreamEvent>(
    (events) => get().applyStreamEvents(events),
  );
  get().abortControllers.set(conversationId, abortController);
  let cursor = afterSequence;
  let attempt = 0;
  try {
    while (!abortController.signal.aborted) {
      try {
        cursor = await streamConversation(conversationId, {
          afterSequence: cursor,
          targetRunId: runId,
          signal: abortController.signal,
          onEvent: batchEvent,
        });
        attempt = 0;
      } catch (error) {
        if (abortController.signal.aborted || isAbortError(error)) return;
        attempt += 1;
      }

      let snapshot: ConversationDetail | null = null;
      try {
        snapshot = await getConversation(conversationId);
        get().loadConversation(snapshot);
        cursor = Math.max(cursor, snapshot.cursor || 0);
      } catch {
        if (abortController.signal.aborted) return;
      }
      const run = snapshot?.runs.find((item) => item.id === runId);
      if (!run || !isFollowableRun(run.status)) return;
      await waitForRetry(Math.min(4_000, 250 * (2 ** Math.min(attempt, 4))), abortController.signal);
    }
  } finally {
    if (get().abortControllers.get(conversationId) === abortController) {
      get().abortControllers.delete(conversationId);
    }
  }
}

function isFollowableRun(status: ConversationRun["status"]): boolean {
  return ["created", "queued", "running", "cancelling"].includes(status);
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function waitForRetry(duration: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const timer = globalThis.setTimeout(resolve, duration);
    signal.addEventListener("abort", () => {
      globalThis.clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}
