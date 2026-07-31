import { z } from "zod";

import {
  zApprovalItem,
  zArtifact,
  zEvidenceResponse,
  zFunctionCallItem,
  zFunctionCallOutputItem,
  zMessageItem,
  zPlanItem,
  zQuestionItem,
  zRunProjection,
  zRunTraceResponse,
  zRuntimeEvent,
} from "../../lib/api/generated/zod.gen";
import type {
  AgentRunTrace,
  ConversationArtifact,
  ConversationEvidence,
  ConversationRun,
  ConversationRunItem,
  RunItemDeltaEnvelope,
  RuntimeEventEnvelope,
} from "../../types/conversation";

/**
 * OpenAPI owns every durable HTTP/SSE contract. This local schema is limited to
 * the process-local text delta, which is intentionally not a durable API item.
 */
const runItemSchema = z.discriminatedUnion("type", [
  zMessageItem,
  zPlanItem,
  zFunctionCallItem,
  zFunctionCallOutputItem,
  zApprovalItem,
  zQuestionItem,
]);

const runItemDeltaSchema = z.object({
  session_id: z.string(),
  run_id: z.string(),
  turn_id: z.string().nullable().optional(),
  item_id: z.string(),
  item_type: z.enum([
    "message",
    "plan",
    "function_call",
    "function_call_output",
    "approval",
    "question",
  ]),
  field: z.literal("content"),
  revision: z.number().int().positive(),
  offset: z.number().int().nonnegative(),
  content: z.string(),
}).strict();

export const parseConversationRun = (value: unknown): ConversationRun => {
  const run = zRunProjection.parse(value);
  return {
    ...run,
    current_turn_id: run.current_turn_id ?? null,
    result: run.result ?? {},
    error: run.error ?? null,
  };
};

export const parseConversationRunItem = (value: unknown): ConversationRunItem => {
  const item = runItemSchema.parse(value);
  const base = {
    ...item,
    turn_id: item.turn_id ?? null,
    completed_at: item.completed_at ?? null,
  };
  switch (item.type) {
    case "message":
      return {
        ...base,
        type: "message",
        payload: {
          ...item.payload,
          content: item.payload.content,
          evidence: item.payload.evidence ?? [],
          artifact_refs: item.payload.artifact_refs ?? [],
          limitation_codes: item.payload.limitation_codes ?? [],
        },
      } as ConversationRunItem;
    case "plan":
      return {
        ...base,
        type: "plan",
        payload: { ...item.payload, steps: item.payload.steps ?? [] },
      } as ConversationRunItem;
    case "function_call":
      return {
        ...base,
        type: "function_call",
        payload: { ...item.payload, arguments: item.payload.arguments ?? {} },
      } as ConversationRunItem;
    case "function_call_output":
      return {
        ...base,
        type: "function_call_output",
        payload: { ...item.payload, artifact_refs: item.payload.artifact_refs ?? [] },
      } as ConversationRunItem;
    case "approval":
      return {
        ...base,
        type: "approval",
        payload: { ...item.payload, requested_action: item.payload.requested_action ?? {} },
      } as ConversationRunItem;
    case "question":
      return {
        ...base,
        type: "question",
        payload: { ...item.payload, options: item.payload.options ?? [] },
      } as ConversationRunItem;
  }
};

export const parseConversationArtifact = (value: unknown): ConversationArtifact => {
  const artifact = zArtifact.parse(value);
  return {
    ...artifact,
    turn_id: artifact.turn_id ?? null,
    semantic_key: artifact.semantic_key ?? null,
    summary: artifact.summary ?? null,
    payload: artifact.payload ?? {},
    payload_ref: artifact.payload_ref ?? null,
    provenance: artifact.provenance ?? {},
    relations: artifact.relations ?? [],
  } as ConversationArtifact;
};

export const parseConversationEvidence = (value: unknown): ConversationEvidence =>
  zEvidenceResponse.parse(value);

export const parseAgentRunTrace = (value: unknown): AgentRunTrace => {
  const trace = zRunTraceResponse.parse(value);
  return {
    ...trace,
    spans: trace.spans.map((span) => ({
      ...span,
      parent_id: span.parent_id ?? null,
      started_at: span.started_at ?? null,
      ended_at: span.ended_at ?? null,
    })),
  };
};

export const parseRuntimeEvent = (value: unknown): RuntimeEventEnvelope => {
  const event = zRuntimeEvent.parse(value);
  return {
    ...event,
    run_id: event.run_id ?? null,
    turn_id: event.turn_id ?? null,
    payload: {
      ...(event.payload?.run ? { run: parseConversationRun(event.payload.run) } : {}),
      ...(event.payload?.item
        ? { item: parseConversationRunItem(event.payload.item) }
        : {}),
    },
  };
};

export const parseRunItemDelta = (value: unknown): RunItemDeltaEnvelope =>
  runItemDeltaSchema.parse(value);
