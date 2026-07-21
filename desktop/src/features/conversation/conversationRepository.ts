import { BASE_URL, ENGINE_TOKEN, request } from "../../lib/api/client";
import { createParser, type EventSourceMessage } from "eventsource-parser";
import type {
  ConversationApproval,
  ConversationArtifact,
  ConversationCreateInput,
  ConversationDetail,
  ConversationEvidence,
  ConversationStreamEvent,
  ConversationSummary,
  ConversationQuestion,
  LiveDeltaEnvelope,
  RuntimeEventEnvelope,
} from "../../types/conversation";

export const listConversations = () => request<ConversationSummary[]>("/conversations");

export const createConversation = async (input: ConversationCreateInput) =>
  normalizeSnapshot(await request<RawSnapshot>("/conversations", {
    method: "POST",
    body: JSON.stringify(input),
  }));

export const getConversation = async (conversationId: string) =>
  normalizeSnapshot(await request<RawSnapshot>(`/conversations/${encodeURIComponent(conversationId)}`));

export const patchConversation = async (
  conversationId: string,
  patch: { title?: string; context_tables?: string[]; archived?: boolean },
) => normalizeSnapshot(await request<RawSnapshot>(`/conversations/${encodeURIComponent(conversationId)}`, {
  method: "PATCH",
  body: JSON.stringify(patch),
}));

export const deleteConversation = (conversationId: string) =>
  request<{ status: "ok" }>(`/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });

export interface AdmitConversationInput {
  content: string;
  idempotency_key: string;
  delivery_mode: "queue" | "steer" | "cancel_and_replace";
  selected_artifact_ids: string[];
  workspace_context: Record<string, unknown>;
  llm_credential_id: string;
  api_base?: string;
  model_name?: string;
}

export interface AdmittedConversationInput {
  session_id: string;
  input_id: string;
  run_id: string;
  user_message_id: string;
  assistant_message_id: string;
  input_sequence: number;
  event_cursor: number;
  stream_path: string;
}

export const admitConversationInput = (conversationId: string, input: AdmitConversationInput) =>
  request<AdmittedConversationInput>(`/conversations/${encodeURIComponent(conversationId)}/inputs`, {
    method: "POST",
    body: JSON.stringify(input),
  });

export const selectConversationArtifact = (conversationId: string, artifactId: string) =>
  request<{ session_id: string; artifact_id: string }>(
    `/conversations/${encodeURIComponent(conversationId)}/artifact-selection`,
    { method: "POST", body: JSON.stringify({ artifact_id: artifactId }) },
  );

export const resolveConversationApproval = (
  approvalId: string,
  expectedVersion: number,
  approved: boolean,
  note?: string,
) => request<ConversationApproval>(`/approvals/${encodeURIComponent(approvalId)}/resolve`, {
  method: "POST",
  body: JSON.stringify({
    expected_version: expectedVersion,
    decision: approved ? "approve" : "reject",
    note: note || null,
  }),
});

export const resolveConversationQuestion = (
  questionId: string,
  expectedVersion: number,
  response: { selected_value?: string; text?: string },
) => request<ConversationQuestion>(`/questions/${encodeURIComponent(questionId)}/resolve`, {
  method: "POST",
  body: JSON.stringify({ expected_version: expectedVersion, ...response }),
});

export const cancelConversationRun = (runId: string) =>
  request<{ run_id: string; status: string; version: number }>(
    `/runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );

export async function streamConversation(
  conversationId: string,
  options: {
    afterSequence: number;
    targetRunId: string;
    signal?: AbortSignal;
    onEvent: (event: ConversationStreamEvent) => void;
  },
): Promise<number> {
  const response = await fetch(
    `${BASE_URL}/conversations/${encodeURIComponent(conversationId)}/stream?after_sequence=${options.afterSequence}`,
    {
      headers: {
        "X-Local-Token": ENGINE_TOKEN,
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
      reachedBoundary = parsed.event.run_id === options.targetRunId && [
        "run.completed",
        "run.failed",
        "run.cancelled",
        "approval.requested",
        "question.requested",
      ].includes(parsed.event.event_type);
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
  const payload = JSON.parse(message.data) as unknown;
  if (message.event === "live.delta") {
    return { kind: "delta", delta: payload as LiveDeltaEnvelope };
  }
  return { kind: "event", event: payload as RuntimeEventEnvelope };
}

type RawSnapshot = {
  protocol_version: 1;
  session: {
    id: string;
    datasource_id: string;
    title: string;
    context_epoch: number;
    selected_artifact_id: string | null;
    context_tables: string[];
  };
  messages: Array<Record<string, unknown>>;
  runs: Array<Record<string, unknown>>;
  activities: ConversationDetail["activities"];
  artifacts: Array<Record<string, unknown>>;
  evidence: ConversationEvidence[];
  approvals: ConversationApproval[];
  questions: ConversationDetail["questions"];
  cursor: number;
};

function normalizeSnapshot(raw: RawSnapshot): ConversationDetail {
  const sessionId = raw.session.id;
  const approvalsByRun = new Map(raw.approvals.map((approval) => [approval.run_id, approval]));
  const evidenceByRun = new Map<string, ConversationEvidence[]>();
  for (const evidence of raw.evidence) {
    if (evidence.run_id) {
      evidenceByRun.set(evidence.run_id, [...(evidenceByRun.get(evidence.run_id) || []), evidence]);
    }
  }
  const artifacts: ConversationArtifact[] = raw.artifacts.map((item, index) => {
    const relations: NonNullable<ConversationArtifact["relations"]> = Array.isArray(item.relations)
      ? item.relations as NonNullable<ConversationArtifact["relations"]>
      : [];
    return {
      id: String(item.id),
      conversation_id: sessionId,
      run_id: String(item.run_id),
      turn_id: item.turn_id ? String(item.turn_id) : null,
      semantic_id: item.semantic_key ? String(item.semantic_key) : null,
      version: Number(item.version || 1),
      type: String(item.type) as ConversationArtifact["type"],
      title: String(item.title || "工件"),
      status: String(item.status || "completed") as ConversationArtifact["status"],
      sequence: index + 1,
      summary: item.summary ? String(item.summary) : null,
      payload: record(item.payload),
      payload_ref: item.payload_ref ? String(item.payload_ref) : null,
      provenance: record(item.provenance),
      relations,
      depends_on: relations.map((relation) => relation.artifact_id),
      created_at: null,
    };
  });
  return {
    protocol_version: 1,
    id: sessionId,
    title: raw.session.title,
    datasource_id: raw.session.datasource_id,
    context_tables: raw.session.context_tables || [],
    selected_artifact_id: raw.session.selected_artifact_id,
    context_epoch: raw.session.context_epoch,
    messages: raw.messages.map((item) => ({
      id: String(item.id), conversation_id: sessionId,
      role: String(item.role) as ConversationDetail["messages"][number]["role"],
      content: String(item.content || ""),
      status: String(item.status) as ConversationDetail["messages"][number]["status"],
      sequence: Number(item.sequence),
      created_at: item.created_at ? String(item.created_at) : null,
      updated_at: item.updated_at ? String(item.updated_at) : null,
    })),
    runs: raw.runs.map((item) => {
      const result = record(item.result);
      const rawAnswer = record(result.answer);
      const runId = String(item.id);
      return {
        id: runId, conversation_id: sessionId, input_id: String(item.input_id),
        session_sequence: Number(item.session_sequence),
        user_message_id: String(item.user_message_id),
        assistant_message_id: String(item.assistant_message_id),
        datasource_id: String(item.datasource_id || raw.session.datasource_id),
        question: String(item.question || ""),
        status: String(item.status) as ConversationDetail["runs"][number]["status"],
        completion_disposition: result.completion_disposition
          ? String(result.completion_disposition) as ConversationDetail["runs"][number]["completion_disposition"]
          : null,
        limitation_codes: Array.isArray(result.limitation_codes)
          ? result.limitation_codes.map(String) as NonNullable<ConversationDetail["runs"][number]["limitation_codes"]>
          : [],
        version: Number(item.version || 0),
        current_turn_id: item.current_turn_id ? String(item.current_turn_id) : null,
        cancel_requested: Boolean(item.cancel_requested),
        error_code: record(item.error).code ? String(record(item.error).code) : null,
        error_message: record(item.error).message ? String(record(item.error).message) : null,
        answer: rawAnswer.text ? {
          answer: String(rawAnswer.text),
          evidence: evidenceByRun.get(runId) || [],
          key_findings: Array.isArray(rawAnswer.key_findings) ? rawAnswer.key_findings.map(String) : [],
          caveats: Array.isArray(rawAnswer.caveats) ? rawAnswer.caveats.map(String) : [],
          recommendations: Array.isArray(rawAnswer.recommendations) ? rawAnswer.recommendations.map(String) : [],
          follow_up_questions: Array.isArray(rawAnswer.follow_up_questions)
            ? rawAnswer.follow_up_questions.map(String)
            : [],
        } : null,
        approval: approvalsByRun.get(runId) || null,
      };
    }),
    activities: raw.activities || [],
    artifacts,
    evidence: raw.evidence || [],
    approvals: raw.approvals || [],
    questions: raw.questions || [],
    cursor: raw.cursor,
  };
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}
