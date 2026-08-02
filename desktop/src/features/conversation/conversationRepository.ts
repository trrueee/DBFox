import { createParser, type EventSourceMessage } from "eventsource-parser";
import { fetchEnginePath } from "../../lib/api/client";
import {
  admitConversationInputApiV1ConversationsConversationIdInputsPost,
  cancelRunApiV1RunsRunIdCancelPost,
  createConversationApiV1ConversationsPost,
  deleteConversationApiV1ConversationsConversationIdDelete,
  getConversationApiV1ConversationsConversationIdGet,
  getConversationHistoryApiV1ConversationsConversationIdHistoryGet,
  getRunArtifactsApiV1ConversationsConversationIdRunsRunIdArtifactsGet,
  getRunEvidenceApiV1ConversationsConversationIdRunsRunIdEvidenceGet,
  listConversationsApiV1ConversationsGet,
  patchConversationApiV1ConversationsConversationIdPatch,
  resolveApprovalApiV1ApprovalsApprovalIdResolvePost,
  resolveQuestionApiV1QuestionsQuestionIdResolvePost,
  selectConversationArtifactApiV1ConversationsConversationIdArtifactSelectionPost,
} from "../../lib/api/generated/sdk.gen";
import type {
  ConversationInputRequest,
  ConversationSnapshotResponse,
} from "../../lib/api/generated/types.gen";
import type {
  ConversationCreateInput,
  ConversationDetail,
  ConversationRun,
  ConversationRunItem,
  ConversationStreamEvent,
  ConversationSummary,
} from "../../types/conversation";
import {
  parseConversationArtifact,
  parseConversationEvidence,
  parseConversationRun,
  parseConversationRunItem,
  parseRunItemDelta,
  parseRuntimeEvent,
} from "./conversationWireSchema";
import { isFollowableRun } from "./conversationState";

export const listConversations = async (): Promise<ConversationSummary[]> => {
  const { data } = await listConversationsApiV1ConversationsGet({
    throwOnError: true,
  });
  return data;
};

export const createConversation = async (input: ConversationCreateInput) => {
  const { data } = await createConversationApiV1ConversationsPost({
    body: input,
    throwOnError: true,
  });
  return normalizeSnapshot(data);
};

export const getConversation = async (conversationId: string) => {
  const { data } = await getConversationApiV1ConversationsConversationIdGet({
    path: { conversation_id: conversationId },
    throwOnError: true,
  });
  return normalizeSnapshot(data);
};

export const getConversationHistory = async (
  conversationId: string,
  options: {
    beforeItemSequence?: number | null;
    beforeRunSequence?: number | null;
    itemLimit?: number;
    runLimit?: number;
  },
) => {
  const { data } = await getConversationHistoryApiV1ConversationsConversationIdHistoryGet({
    path: { conversation_id: conversationId },
    query: {
      before_item_sequence: options.beforeItemSequence ?? undefined,
      before_run_sequence: options.beforeRunSequence ?? undefined,
      item_limit: options.itemLimit ?? 200,
      run_limit: options.runLimit ?? 20,
    },
    throwOnError: true,
  });
  return normalizeSnapshot(data);
};

export const getConversationRunArtifacts = async (
  conversationId: string,
  runId: string,
) => {
  const { data } = await getRunArtifactsApiV1ConversationsConversationIdRunsRunIdArtifactsGet({
    path: { conversation_id: conversationId, run_id: runId },
    throwOnError: true,
  });
  return data.map(parseConversationArtifact);
};

export const getConversationRunEvidence = async (
  conversationId: string,
  runId: string,
) => {
  const { data } = await getRunEvidenceApiV1ConversationsConversationIdRunsRunIdEvidenceGet({
    path: { conversation_id: conversationId, run_id: runId },
    throwOnError: true,
  });
  return data.map(parseConversationEvidence);
};

export const patchConversation = async (
  conversationId: string,
  patch: { title?: string; context_tables?: string[]; archived?: boolean },
) => {
  const { data } = await patchConversationApiV1ConversationsConversationIdPatch({
    path: { conversation_id: conversationId },
    body: patch,
    throwOnError: true,
  });
  return normalizeSnapshot(data);
};

export const deleteConversation = async (conversationId: string) => {
  const { data } = await deleteConversationApiV1ConversationsConversationIdDelete({
    path: { conversation_id: conversationId },
    throwOnError: true,
  });
  return data;
};

export type AdmitConversationInput = ConversationInputRequest;

export interface AdmittedConversationInput {
  session_id: string;
  input_id: string;
  run_id: string;
  user_message_id: string;
  input_sequence: number;
  event_cursor: number;
  stream_path: string;
  projection: {
    protocol_version: 2;
    cursor: number;
    items: ConversationRunItem[];
    runs: ConversationRun[];
  };
}

export const admitConversationInput = async (
  conversationId: string,
  input: AdmitConversationInput,
) => {
  const { data } = await admitConversationInputApiV1ConversationsConversationIdInputsPost({
    path: { conversation_id: conversationId },
    body: input,
    throwOnError: true,
  });
  const admitted: AdmittedConversationInput = {
    ...data,
    projection: {
      ...data.projection,
      items: data.projection.items.map(parseConversationRunItem),
      runs: data.projection.runs.map(parseConversationRun),
    },
  };
  requireProtocolVersion(admitted.projection.protocol_version);
  return admitted;
};

export const selectConversationArtifact = async (
  conversationId: string,
  artifactId: string,
) => {
  const { data } = await selectConversationArtifactApiV1ConversationsConversationIdArtifactSelectionPost({
    path: { conversation_id: conversationId },
    body: { artifact_id: artifactId },
    throwOnError: true,
  });
  return data;
};

export const resolveConversationApproval = (
  approvalId: string,
  expectedVersion: number,
  approved: boolean,
  note?: string,
) => resolveApprovalApiV1ApprovalsApprovalIdResolvePost({
  path: { approval_id: approvalId },
  body: {
    expected_version: expectedVersion,
    decision: approved ? "approve" : "reject",
    note: note || null,
  },
  throwOnError: true,
}).then(({ data }) => data);

export const resolveConversationQuestion = (
  questionId: string,
  expectedVersion: number,
  response: { selected_value?: string; text?: string },
) => resolveQuestionApiV1QuestionsQuestionIdResolvePost({
  path: { question_id: questionId },
  body: { expected_version: expectedVersion, ...response },
  throwOnError: true,
}).then(({ data }) => data);

export const cancelConversationRun = (runId: string) =>
  cancelRunApiV1RunsRunIdCancelPost({
    path: { run_id: runId },
    throwOnError: true,
  }).then(({ data }) => data);

export async function streamConversation(
  conversationId: string,
  options: {
    afterSequence: number;
    targetRunId: string;
    signal?: AbortSignal;
    onEvent: (event: ConversationStreamEvent) => void;
  },
): Promise<number> {
  const response = await fetchEnginePath(
    `/conversations/${encodeURIComponent(conversationId)}/stream?after_sequence=${options.afterSequence}`,
    {
      headers: {
        "Last-Event-ID": String(options.afterSequence),
      },
      signal: options.signal,
    },
  );
  if (!response.ok) throw new Error("无法连接智能分析流。");
  if (!response.body) throw new Error("当前环境不支持流式响应。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let cursor = options.afterSequence;
  let reachedBoundary = false;
  const parser = createParser({
    maxBufferSize: 1024 * 1024,
    onEvent(message) {
      const parsed = parseSseMessage(message);
      if (!parsed) return;
      options.onEvent(parsed);
      if (parsed.kind !== "event") return;
      cursor = Math.max(cursor, parsed.event.sequence);
      const projectedRun = parsed.event.payload.run;
      reachedBoundary ||= parsed.event.run_id === options.targetRunId
        && Boolean(projectedRun)
        && !isFollowableRun(projectedRun!.status);
    },
  });
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        const tail = decoder.decode();
        if (tail) parser.feed(tail);
        parser.reset({ consume: true });
        return cursor;
      }
      parser.feed(decoder.decode(value, { stream: true }));
      if (reachedBoundary) {
        await reader.cancel();
        return cursor;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseMessage(message: EventSourceMessage): ConversationStreamEvent | null {
  if (!message.data) return null;
  const payload: unknown = JSON.parse(message.data);
  if (message.event === "run.item.delta") {
    return { kind: "delta", delta: parseRunItemDelta(payload) };
  }
  return { kind: "event", event: parseRuntimeEvent(payload) };
}

function normalizeSnapshot(raw: ConversationSnapshotResponse): ConversationDetail {
  requireProtocolVersion(raw.protocol_version);
  return {
    protocol_version: 2,
    id: raw.session.id,
    title: raw.session.title,
    datasource_id: raw.session.datasource_id,
    context_tables: raw.session.context_tables || [],
    selected_artifact_id: raw.session.selected_artifact_id,
    context_epoch: raw.session.context_epoch,
    runs: raw.runs.map(parseConversationRun),
    items: raw.items.map(parseConversationRunItem),
    pagination: {
      items: {
        has_more: raw.pagination.items.has_more,
        next_before_sequence: raw.pagination.items.next_before_sequence ?? null,
      },
      runs: {
        has_more: raw.pagination.runs.has_more,
        next_before_sequence: raw.pagination.runs.next_before_sequence ?? null,
      },
    },
    cursor: raw.cursor,
  };
}

function requireProtocolVersion(version: number): asserts version is 2 {
  if (version !== 2) {
    throw new Error(`不支持的 Agent 时间线协议版本：${version}`);
  }
}
