import { create } from "zustand";
import { getStoredApiConfig } from "../components/SettingsDialog";
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  startConversationMessageStream,
} from "../features/conversation/conversationRepository";
import { createStreamEventBatcher } from "../features/conversation/streamEventBatcher";
import { agentApi } from "../lib/api/agent";
import type {
  ConversationArtifact,
  ConversationDetail,
  ConversationMessage,
  ConversationRun,
  ConversationStreamEvent,
  ConversationSummary,
} from "../types/conversation";
import { useDatasourceStore } from "./datasourceStore";

interface ConversationState {
  summaries: ConversationSummary[];
  activeConversationId: string | null;
  detailById: Record<string, ConversationDetail>;
  messagesById: Record<string, ConversationMessage>;
  runsById: Record<string, ConversationRun>;
  artifactsById: Record<string, ConversationArtifact>;
  abortControllers: Map<string, AbortController>;
}

interface ConversationActions {
  initConversations: () => Promise<void>;
  openConversation: (conversationId: string) => Promise<ConversationDetail>;
  createAndOpenConversation: (question: string, contextTables: string[]) => Promise<ConversationDetail>;
  deleteConversationById: (conversationId: string) => Promise<void>;
  loadConversation: (detail: ConversationDetail) => void;
  sendMessage: (conversationId: string, content: string) => Promise<void>;
  cancelRun: (runId: string) => void;
  resolveApproval: (runId: string, approvalId: string, approved: boolean) => Promise<void>;
  applyStreamEvent: (event: ConversationStreamEvent) => void;
  applyStreamEvents: (events: ConversationStreamEvent[]) => void;
}

export type ConversationStore = ConversationState & ConversationActions;

function answerText(event: ConversationStreamEvent): string | null {
  if (event.answer?.answer) return event.answer.answer;
  if (event.response?.answer?.answer) return event.response.answer.answer;
  if (event.response?.explanation) return event.response.explanation;
  if (event.error) return `Run failed: ${event.error}`;
  return null;
}

function messageStatusForEvent(event: ConversationStreamEvent): ConversationMessage["status"] {
  if (event.type === "agent.run.failed") return "failed";
  if (event.type === "agent.run.cancelled") return "cancelled";
  if (event.type === "agent.answer.completed" || event.type === "agent.run.completed") return "completed";
  return "streaming";
}

function sequenceAfter(detail: ConversationDetail | undefined): number {
  return (detail?.messages.reduce((max, message) => Math.max(max, message.sequence), 0) || 0) + 1;
}

function ensureStreamMessages(state: ConversationStore, event: ConversationStreamEvent): ConversationStore {
  const conversationId = event.conversation_id || event.response?.conversation_id || "";
  if (!conversationId || !event.user_message_id || !event.assistant_message_id) return state;

  const detail = state.detailById[conversationId];
  if (!detail) return state;

  let nextMessagesById = state.messagesById;
  let nextDetail = detail;
  const addMessage = (message: ConversationMessage) => {
    nextMessagesById = { ...nextMessagesById, [message.id]: message };
    nextDetail = { ...nextDetail, messages: [...nextDetail.messages, message] };
  };

  if (!nextMessagesById[event.user_message_id]) {
    addMessage({
      id: event.user_message_id,
      conversation_id: conversationId,
      role: "user",
      content: typeof event.step?.question === "string" ? event.step.question : "",
      status: "completed",
      sequence: sequenceAfter(nextDetail),
      created_at: null,
      updated_at: null,
    });
  }
  if (!nextMessagesById[event.assistant_message_id]) {
    addMessage({
      id: event.assistant_message_id,
      conversation_id: conversationId,
      role: "assistant",
      content: "",
      status: "streaming",
      sequence: sequenceAfter(nextDetail),
      created_at: null,
      updated_at: null,
    });
  }

  if (nextMessagesById === state.messagesById && nextDetail === detail) return state;

  return {
    ...state,
    detailById: { ...state.detailById, [conversationId]: nextDetail },
    messagesById: nextMessagesById,
  };
}

function sameMessagePatch(current: ConversationMessage, patch: Partial<ConversationMessage>): boolean {
  return Object.entries(patch).every(([key, value]) => current[key as keyof ConversationMessage] === value);
}

function upsertMessage(
  state: ConversationStore,
  messageId: string,
  patch: Partial<ConversationMessage>,
): ConversationStore {
  const current = state.messagesById[messageId];
  if (!current) return state;
  if (sameMessagePatch(current, patch)) return state;
  const nextMessage = { ...current, ...patch };
  const detail = state.detailById[nextMessage.conversation_id];
  return {
    ...state,
    messagesById: { ...state.messagesById, [messageId]: nextMessage },
    detailById: detail
      ? {
          ...state.detailById,
          [detail.id]: {
            ...detail,
            messages: detail.messages.map((message) => (message.id === messageId ? nextMessage : message)),
          },
        }
      : state.detailById,
  };
}

function runEventKey(event: ConversationStreamEvent): string {
  return event.event_id || `${event.type}:${event.sequence ?? 0}`;
}

function withRunEvent(run: ConversationRun, event: ConversationStreamEvent): ConversationRun {
  const events = run.events || [];
  const key = runEventKey(event);
  if (events.some((item) => runEventKey(item as ConversationStreamEvent) === key)) return run;
  return {
    ...run,
    events: [...events, event].sort((a, b) => (a.sequence || 0) - (b.sequence || 0)),
  };
}

function runStatusForApprovalEvent(event: ConversationStreamEvent): ConversationRun["status"] | null {
  if (event.type === "agent.approval.required" || event.type === "agent.run.waiting_approval") return "waiting_approval";
  if (event.type === "agent.run.resumed") return "running";
  if (event.type === "agent.approval.resolved" && event.approval?.status === "rejected") return "failed";
  return null;
}

function withConversationRunContext(event: ConversationStreamEvent, run: ConversationRun): ConversationStreamEvent {
  return {
    ...event,
    conversation_id: event.conversation_id || run.conversation_id,
    user_message_id: event.user_message_id || run.user_message_id,
    assistant_message_id: event.assistant_message_id || run.assistant_message_id,
    message_id: event.message_id || run.assistant_message_id || undefined,
  };
}

function upsertRun(state: ConversationStore, conversationId: string, run: ConversationRun): ConversationStore {
  const current = state.runsById[run.id];
  if (current === run) return state;
  const detail = conversationId ? state.detailById[conversationId] : undefined;
  return {
    ...state,
    runsById: { ...state.runsById, [run.id]: run },
    detailById: detail
      ? {
          ...state.detailById,
          [conversationId]: {
            ...detail,
            runs: detail.runs.some((item) => item.id === run.id)
              ? detail.runs.map((item) => (item.id === run.id ? run : item))
              : [...detail.runs, run],
          },
        }
      : state.detailById,
  };
}

function sameRunPatch(current: ConversationRun, patch: Partial<ConversationRun>): boolean {
  return Object.entries(patch).every(([key, value]) => current[key as keyof ConversationRun] === value);
}

function reduceStreamEvent(state: ConversationStore, event: ConversationStreamEvent): ConversationStore {
  let next = ensureStreamMessages(state, event);
  const conversationId = event.conversation_id || event.response?.conversation_id || "";
  const messageId = event.message_id || event.assistant_message_id || event.response?.assistant_message_id || null;
  const text = answerText(event);

  if (event.run_id) {
    const current = next.runsById[event.run_id];
    const approval = event.approval || event.response?.approval || current?.approval || null;
    const approvalStatus = runStatusForApprovalEvent(event);
    const answer = event.answer || event.response?.answer || current?.answer || null;
    const run: ConversationRun = current || {
      id: event.run_id,
      conversation_id: conversationId,
      datasource_id: "",
      question: typeof event.step?.question === "string" ? event.step.question : "",
      status: "running",
      user_message_id: event.user_message_id,
      assistant_message_id: event.assistant_message_id,
      events: [],
    };
    const runPatch: Partial<ConversationRun> = {
      status: approvalStatus || run.status,
      approval,
      answer,
    };
    const candidateBase = { ...run, ...runPatch };
    const candidate = withRunEvent(candidateBase, event);
    if (!current || candidate !== candidateBase || !sameRunPatch(current, runPatch)) {
      next = upsertRun(next, conversationId, candidate);
    }
  }

  if (
    event.type === "agent.run.completed" ||
    event.type === "agent.run.failed" ||
    event.type === "agent.run.cancelled"
  ) {
    const status =
      event.type === "agent.run.completed"
        ? "completed"
        : event.type === "agent.run.cancelled"
          ? "cancelled"
          : "failed";
    const currentRun = next.runsById[event.run_id];
    if (
      currentRun &&
      !sameRunPatch(currentRun, {
        status,
        error_message: event.error || currentRun.error_message,
        error_code: event.code || currentRun.error_code,
      })
    ) {
      next = upsertRun(next, conversationId, {
        ...currentRun,
        status,
        error_message: event.error || currentRun.error_message,
        error_code: event.code || currentRun.error_code,
      });
    }
  }

  if (messageId && text) {
    next = upsertMessage(next, messageId, { content: text, status: messageStatusForEvent(event) });
  }

  if (event.artifact) {
    const artifact: ConversationArtifact = {
      id: event.artifact.id,
      conversation_id: conversationId,
      run_id: event.run_id,
      message_id: messageId,
      semantic_id: event.artifact.semantic_id || null,
      type: event.artifact.type as ConversationArtifact["type"],
      title: event.artifact.title,
      status: "completed",
      sequence: event.sequence,
      payload: event.artifact.payload || {},
      presentation: event.artifact.presentation as unknown as Record<string, unknown>,
      depends_on: Array.isArray(event.artifact.depends_on) ? event.artifact.depends_on : [],
      refs: event.artifact.refs || {},
      created_at: null,
    };
    const detail = conversationId ? next.detailById[conversationId] : undefined;
    next = {
      ...next,
      artifactsById: { ...next.artifactsById, [artifact.id]: artifact },
      detailById: detail
        ? {
            ...next.detailById,
            [conversationId]: {
              ...detail,
              artifacts: detail.artifacts.some((item) => item.id === artifact.id)
                ? detail.artifacts.map((item) => (item.id === artifact.id ? artifact : item))
                : [...detail.artifacts, artifact],
            },
          }
        : next.detailById,
    };
  }

  return next;
}

export const useConversationStore = create<ConversationStore>()((set, get) => ({
  summaries: [],
  activeConversationId: null,
  detailById: {},
  messagesById: {},
  runsById: {},
  artifactsById: {},
  abortControllers: new Map(),

  initConversations: async () => {
    const summaries = await listConversations();
    set({ summaries });
  },

  openConversation: async (conversationId) => {
    const detail = await getConversation(conversationId);
    get().loadConversation(detail);
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
    const messagesById = { ...get().messagesById };
    const runsById = { ...get().runsById };
    const artifactsById = { ...get().artifactsById };
    for (const message of detail.messages) messagesById[message.id] = message;
    for (const run of detail.runs) runsById[run.id] = run;
    for (const artifact of detail.artifacts) artifactsById[artifact.id] = artifact;
    set((state) => ({
      activeConversationId: detail.id,
      detailById: { ...state.detailById, [detail.id]: detail },
      messagesById,
      runsById,
      artifactsById,
    }));
  },

  sendMessage: async (conversationId, content) => {
    const llm = getStoredApiConfig();
    const abortController = new AbortController();
    const batchEvent = createStreamEventBatcher<ConversationStreamEvent>((events) => get().applyStreamEvents(events));
    get().abortControllers.set(conversationId, abortController);
    try {
      await startConversationMessageStream(
        conversationId,
        {
          content,
          api_key: llm.apiKey || undefined,
          api_base: llm.apiBase || undefined,
          model_name: llm.modelName || undefined,
          execute: true,
        },
        { signal: abortController.signal, onEvent: batchEvent },
      );
      await get().openConversation(conversationId);
      await get().initConversations();
    } finally {
      get().abortControllers.delete(conversationId);
    }
  },

  cancelRun: (runId) => {
    for (const controller of get().abortControllers.values()) controller.abort();
    set((state) => ({
      runsById: state.runsById[runId]
        ? { ...state.runsById, [runId]: { ...state.runsById[runId], status: "cancelled" } }
        : state.runsById,
    }));
  },

  resolveApproval: async (runId, approvalId, approved) => {
    const run = get().runsById[runId];
    if (!run) return;
    if (approved) {
      await agentApi.streamResumeAgentRun(runId, approvalId, {
        note: "Approved in DBFox UI",
        onEvent: (event) => get().applyStreamEvent(withConversationRunContext(event, run)),
      });
      await get().openConversation(run.conversation_id);
      await get().initConversations();
      return;
    }

    const response = await agentApi.rejectAgentApproval(runId, approvalId, "Rejected in DBFox UI");
    const rejectedApproval =
      response.approval || run.approval
        ? {
            ...(run.approval || response.approval!),
            ...(response.approval || {}),
            status: "rejected" as const,
          }
        : null;
    set((state) => {
      const current = state.runsById[runId];
      if (!current) return state;
      let next = upsertRun(state, current.conversation_id, {
        ...current,
        status: "failed",
        approval: rejectedApproval,
        error_message: "用户拒绝执行此操作。",
      });
      if (current.assistant_message_id) {
        next = upsertMessage(next, current.assistant_message_id, {
          content: "已拒绝执行操作。",
          status: "failed",
        });
      }
      return next;
    });
  },

  applyStreamEvent: (event) => {
    set((state) => reduceStreamEvent(state, event));
  },

  applyStreamEvents: (events) => {
    if (events.length === 0) return;
    set((state) => events.reduce(reduceStreamEvent, state));
  },
}));
