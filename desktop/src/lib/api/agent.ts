import { BASE_URL, ENGINE_TOKEN, request } from "./client";
import type {
  AgentArtifact,
  AgentArtifactRecord,
  AgentApproval,
  AgentCheckpoint,
  AgentKernelThreadState,
  AgentRunConfig,
  AgentRunDraftState,
  AgentRunResponse,
  AgentRuntimeEvent,
  AgentRuntimeEventRecord,
  AgentSessionRunSummary,
  AgentTraceEventRecord,
} from "./types";

export function createAgentRunDraft(question: string): AgentRunDraftState {
  return {
    status: "running",
    question,
    events: [],
    artifacts: [],
    answer: null,
    response: null,
    approval: null,
    checkpoint: null,
    error: null,
  };
}

const EVENT_REDUCERS: Record<
  string,
  (next: AgentRunDraftState, event: AgentRuntimeEvent, draft: AgentRunDraftState) => AgentRunDraftState
> = {
  "agent.run.started": (next, event, draft) => {
    const question = typeof event.step?.question === "string" ? event.step.question : draft.question;
    return { ...next, question, status: "running", error: null };
  },
  "agent.context.update": (next, event) => {
    const summary = typeof event.step?.summary === "string" ? event.step.summary : null;
    const rawLens = event.step?.task_lens as Record<string, unknown> | undefined;
    const taskLens = rawLens && typeof rawLens === "object"
      ? {
          goal: typeof rawLens.goal === "string" ? rawLens.goal : undefined,
          current_focus: typeof rawLens.current_focus === "string" ? rawLens.current_focus : undefined,
          next_likely: typeof rawLens.next_likely === "string" ? rawLens.next_likely : undefined,
          missing_evidence: Array.isArray(rawLens.missing_evidence)
            ? rawLens.missing_evidence.filter((v: unknown): v is string => typeof v === "string")
            : undefined,
        }
      : next.taskLens;
    if (!summary && !taskLens) return next;
    return {
      ...next,
      ...(summary ? { contextSummary: summary } : {}),
      ...(taskLens ? { taskLens } : {}),
    };
  },
  "agent.artifact.created": (next, event, draft) => {
    if (!event.artifact) return next;
    return {
      ...next,
      artifacts: mergeArtifacts(draft.artifacts, [event.artifact]),
    };
  },
  "agent.artifact.delta": (next, event, draft) => {
    if (!event.artifact_delta) return next;
    const delta = event.artifact_delta as { artifact_id?: string; payload_merge?: Record<string, unknown> };
    const artifactId = delta.artifact_id;
    const payloadMerge = delta.payload_merge;
    if (!artifactId || !payloadMerge) return next;
    return {
      ...next,
      artifacts: mergeArtifactDelta(draft.artifacts, artifactId, payloadMerge),
    };
  },
  "agent.answer.completed": (next, event, draft) => {
    return { ...next, answer: event.answer || draft.answer || null };
  },
  "agent.approval.required": (next, event, draft) => {
    return { ...next, approval: mergeApproval(draft.approval, event.approval) };
  },
  "agent.checkpoint.saved": (next, event, draft) => {
    return { ...next, checkpoint: event.checkpoint || draft.checkpoint || null };
  },
  "agent.approval.resolved": (next, event, draft) => {
    const approval = mergeApproval(draft.approval, event.approval);
    return {
      ...next,
      approval,
      error: approval?.id === event.approval?.id && event.approval?.status === "rejected" ? "Approval rejected" : draft.error,
    };
  },
  "agent.run.waiting_approval": (next, event, draft) => {
    return {
      ...next,
      status: "waiting_approval",
      response: event.response || draft.response || null,
      approval: mergeApproval(draft.approval, event.approval || event.response?.approval),
      checkpoint: event.checkpoint || event.response?.checkpoint || draft.checkpoint || null,
      artifacts: mergeArtifacts(draft.artifacts, event.response?.artifacts || []),
      error: null,
    };
  },
  "agent.run.resumed": (next, event, draft) => {
    return {
      ...next,
      status: "running",
      approval: mergeApproval(draft.approval, event.approval),
      checkpoint: event.checkpoint || draft.checkpoint || null,
      error: null,
    };
  },
  "agent.run.completed": (next, event, draft) => {
    if (!event.response) return next;
    return {
      ...next,
      status: "completed",
      response: event.response,
      answer: event.response.answer || draft.answer || null,
      artifacts: mergeArtifacts(draft.artifacts, event.response.artifacts || []),
      error: null,
    };
  },
  "agent.run.failed": (next, event, draft) => {
    return {
      ...next,
      status: "failed",
      response: event.response || draft.response || null,
      answer: event.response?.answer || draft.answer || null,
      artifacts: mergeArtifacts(draft.artifacts, event.response?.artifacts || []),
      error: event.error || event.response?.error || "Agent stream failed.",
    };
  },
};

export function reduceAgentRuntimeEvent(draft: AgentRunDraftState, event: AgentRuntimeEvent): AgentRunDraftState {
  const next: AgentRunDraftState = {
    ...draft,
    runId: event.run_id || draft.runId,
    events: [...draft.events, event],
  };

  const reducer = EVENT_REDUCERS[event.type];
  if (reducer) {
    return reducer(next, event, draft);
  }
  return next;
}

function mergeArtifacts(current: AgentArtifact[], incoming: AgentArtifact[]): AgentArtifact[] {
  const byId = new Map(current.map((artifact) => [artifactKey(artifact), artifact]));
  for (const artifact of incoming) {
    byId.set(artifactKey(artifact), artifact);
  }
  return Array.from(byId.values());
}

export function mergeArtifactDelta(
  artifacts: AgentArtifact[],
  artifactId: string,
  payloadMerge: Record<string, unknown>,
): AgentArtifact[] {
  return artifacts.map((artifact) => {
    if ((artifact.semantic_id || artifact.id) !== artifactId) return artifact;
    const mergedPayload = { ...artifact.payload };
    for (const [key, value] of Object.entries(payloadMerge)) {
      if (Array.isArray(value) && Array.isArray(mergedPayload[key])) {
        // Append list fields (e.g., rows arriving in batches)
        mergedPayload[key] = [...(mergedPayload[key] as unknown[]), ...value];
      } else {
        // Replace scalar fields
        mergedPayload[key] = value;
      }
    }
    return { ...artifact, payload: mergedPayload };
  });
}

function artifactKey(artifact: AgentArtifact): string {
  return artifact.semantic_id || artifact.id;
}

function mergeApproval(
  current: AgentApproval | null | undefined,
  incoming: AgentApproval | null | undefined,
): AgentApproval | null {
  if (!incoming) return current || null;
  if (current?.status === "pending" && current.id !== incoming.id && incoming.status !== "pending") {
    return current;
  }
  return incoming;
}

function buildAgentRunPayload(datasourceId: string, question: string, config?: AgentRunConfig) {
  return {
    datasource_id: datasourceId,
    question,
    session_id: config?.sessionId || config?.followUpContext?.session_id,
    parent_run_id: config?.parentRunId || config?.followUpContext?.parent_run_id,
    follow_up_context: config?.followUpContext,
    api_key: config?.apiKey,
    api_base: config?.apiBase,
    model_name: config?.model,
    workspace_context: config?.workspaceContext,
    optimize_rag: config?.optimizeRag ?? true,
    execute: config?.execute ?? true,
  };
}

function parseSseEvent(rawEvent: string): AgentRuntimeEvent | null {
  const dataLines = rawEvent
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) return null;
  return JSON.parse(dataLines.join("\n")) as AgentRuntimeEvent;
}

async function streamAgentRun(
  datasourceId: string,
  question: string,
  config?: AgentRunConfig,
  options?: { signal?: AbortSignal; onEvent?: (event: AgentRuntimeEvent) => void },
): Promise<AgentRunResponse> {
  return streamAgentEndpoint(
    "/agent/run/stream",
    buildAgentRunPayload(datasourceId, question, config),
    options,
  );
}

export async function streamResumeAgentRun(
  runId: string,
  approvalId: string,
  options?: { signal?: AbortSignal; onEvent?: (event: AgentRuntimeEvent) => void; note?: string | null },
): Promise<AgentRunResponse> {
  return streamAgentEndpoint(
    `/agent/runs/${runId}/resume/stream`,
    {
      run_id: runId,
      approval_id: approvalId,
      approved: true,
      note: options?.note || null,
    },
    options,
  );
}

async function streamAgentEndpoint(
  path: string,
  payload: Record<string, unknown>,
  options?: { signal?: AbortSignal; onEvent?: (event: AgentRuntimeEvent) => void },
): Promise<AgentRunResponse> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Local-Token": ENGINE_TOKEN,
    },
    body: JSON.stringify(payload),
    signal: options?.signal,
  });

  if (!response.ok) {
    const text = await response.text();
    const payload = (() => { if (!text) return null; try { return JSON.parse(text); } catch { return { message: text }; } })();
    const error = new Error(payload?.detail?.message || payload?.message || "Request failed") as Error & { code?: string; checks?: unknown[] };
    error.code = payload?.detail?.code || payload?.code;
    error.checks = payload?.detail?.checks || payload?.checks || [];
    throw error;
  }

  if (!response.body) {
    throw new Error("Agent stream is not supported by this browser runtime.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResponse: AgentRunResponse | null = null;

  const processText = (text: string) => {
    buffer += text;
    buffer = buffer.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (rawEvent) {
        const event = parseSseEvent(rawEvent);
        if (event) {
          options?.onEvent?.(event);
          if (event.response) {
            finalResponse = event.response;
          } else if (event.type === "agent.run.failed") {
            const failed = event as AgentRuntimeEvent & { code?: string };
            const error = new Error(failed.error || "Agent stream failed.") as Error & { code?: string };
            error.code = failed.code;
            throw error;
          }
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      processText(decoder.decode(value, { stream: true }));
    }
    const remaining = decoder.decode();
    if (remaining) processText(remaining);
    if (buffer.trim()) processText("\n\n");
  } finally {
    reader.releaseLock();
  }

  if (!finalResponse) {
    throw new Error("Agent stream ended without a final response.");
  }
  return finalResponse;
}

export const listAgentRunApprovals = (runId: string) =>
  request<AgentApproval[]>(`/agent/runs/${encodeURIComponent(runId)}/approvals`);

export const listAgentRunCheckpoints = (runId: string) =>
  request<AgentCheckpoint[]>(`/agent/runs/${encodeURIComponent(runId)}/checkpoints`);

export const resolveAgentApproval = (
  runId: string,
  approvalId: string,
  decision: "approved" | "rejected",
  note?: string,
) =>
  request<AgentApproval>(`/agent/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });

export const resumeAgentRun = (runId: string, approvalId: string) =>
  request<AgentRunResponse>(`/agent/runs/${encodeURIComponent(runId)}/resume`, {
    method: "POST",
    body: JSON.stringify({ run_id: runId, approval_id: approvalId, approved: true, note: null }),
  });

export const rejectAgentApproval = (
  runId: string,
  approvalId: string,
  note?: string,
) =>
  request<AgentRunResponse>(`/agent/runs/${encodeURIComponent(runId)}/resume`, {
    method: "POST",
    body: JSON.stringify({ run_id: runId, approval_id: approvalId, approved: false, note }),
  });

export const agentApi = {
  runAgentQuery: (datasourceId: string, question: string, config?: AgentRunConfig, signal?: AbortSignal) =>
    request<AgentRunResponse>("/agent/run", {
      method: "POST",
      body: JSON.stringify(buildAgentRunPayload(datasourceId, question, config)),
      signal,
    }),

  streamAgentQuery: (
    datasourceId: string,
    question: string,
    config?: AgentRunConfig,
    options?: { signal?: AbortSignal; onEvent?: (event: AgentRuntimeEvent) => void },
  ) => streamAgentRun(datasourceId, question, config, options),

  getAgentRun: (runId: string) =>
    request<AgentRunResponse | null>(`/agent/runs/${encodeURIComponent(runId)}`),

  listAgentSessionRuns: (sessionId: string) =>
    request<AgentSessionRunSummary[]>(`/agent/sessions/${encodeURIComponent(sessionId)}/runs`),

  getRecentAgentRun: (datasourceId: string) =>
    request<AgentRunResponse | null>(`/agent/runs/recent?datasource_id=${encodeURIComponent(datasourceId)}`),

  getAgentRunArtifacts: (runId: string) =>
    request<AgentArtifactRecord[]>(`/agent/runs/${encodeURIComponent(runId)}/artifacts`),

  getAgentRunEvents: (runId: string) =>
    request<AgentRuntimeEventRecord[]>(`/agent/runs/${encodeURIComponent(runId)}/events`),

  getAgentRunTrace: (runId: string) =>
    request<AgentTraceEventRecord[]>(`/agent/runs/${encodeURIComponent(runId)}/trace`),

  getAgentThreadState: (threadId: string) =>
    request<AgentKernelThreadState>(`/agent/runs/${encodeURIComponent(threadId)}/checkpoints`),

  listAgentRunApprovals,

  listAgentRunCheckpoints,

  resolveAgentApproval,

  resumeAgentRun,

  rejectAgentApproval,

  streamResumeAgentRun,
};

// ---------------------------------------------------------------------------
// LLM Connection Test
// ---------------------------------------------------------------------------

export interface LlmTestRequest {
  api_key: string;
  api_base: string;
  model_name: string;
}

export interface LlmTestResponse {
  ok: boolean;
  model: string;
  api_base: string;
  latency_ms: number;
  error_code: string | null;
  error_message: string | null;
}

export async function testLlmConnection(
  apiKey: string,
  apiBase: string,
  modelName: string,
): Promise<LlmTestResponse> {
  return request<LlmTestResponse>("/agent/llm/test", {
    method: "POST",
    body: JSON.stringify({
      api_key: apiKey,
      api_base: apiBase,
      model_name: modelName,
    }),
  });
}
