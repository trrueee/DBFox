import { BASE_URL, ENGINE_TOKEN, request } from "./client";
import type {
  AgentArtifact,
  AgentArtifactRecord,
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
    error: null,
  };
}

export function reduceAgentRuntimeEvent(draft: AgentRunDraftState, event: AgentRuntimeEvent): AgentRunDraftState {
  const next: AgentRunDraftState = {
    ...draft,
    runId: event.run_id || draft.runId,
    events: [...draft.events, event],
  };

  if (event.type === "agent.run.started") {
    const question = typeof event.step?.question === "string" ? event.step.question : draft.question;
    return { ...next, question, status: "running", error: null };
  }

  if (event.type === "agent.artifact.created" && event.artifact) {
    return {
      ...next,
      artifacts: mergeArtifacts(draft.artifacts, [event.artifact]),
    };
  }

  if (event.type === "agent.answer.completed") {
    return { ...next, answer: event.answer || draft.answer || null };
  }

  if (event.type === "agent.run.completed" && event.response) {
    return {
      ...next,
      status: "completed",
      response: event.response,
      answer: event.response.answer || draft.answer || null,
      artifacts: mergeArtifacts(draft.artifacts, event.response.artifacts || []),
      error: null,
    };
  }

  if (event.type === "agent.run.failed") {
    return {
      ...next,
      status: "failed",
      response: event.response || draft.response || null,
      answer: event.response?.answer || draft.answer || null,
      artifacts: mergeArtifacts(draft.artifacts, event.response?.artifacts || []),
      error: event.error || event.response?.error || "Agent stream failed.",
    };
  }

  return next;
}

function mergeArtifacts(current: AgentArtifact[], incoming: AgentArtifact[]): AgentArtifact[] {
  const byId = new Map(current.map((artifact) => [artifact.id, artifact]));
  for (const artifact of incoming) {
    byId.set(artifact.id, artifact);
  }
  return Array.from(byId.values());
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
  const response = await fetch(`${BASE_URL}/query/agent-run/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Local-Token": ENGINE_TOKEN,
    },
    body: JSON.stringify(buildAgentRunPayload(datasourceId, question, config)),
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
            throw new Error(event.error || "Agent stream failed.");
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

export const agentApi = {
  runAgentQuery: (datasourceId: string, question: string, config?: AgentRunConfig, signal?: AbortSignal) =>
    request<AgentRunResponse>("/query/agent-run", {
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
    request<AgentRunResponse | null>(`/query/agent-runs/${encodeURIComponent(runId)}`),

  listAgentSessionRuns: (sessionId: string) =>
    request<AgentSessionRunSummary[]>(`/query/agent-sessions/${encodeURIComponent(sessionId)}/runs`),

  getRecentAgentRun: (datasourceId: string) =>
    request<AgentRunResponse | null>(`/query/agent-runs/recent?datasource_id=${encodeURIComponent(datasourceId)}`),

  getAgentRunArtifacts: (runId: string) =>
    request<AgentArtifactRecord[]>(`/query/agent-runs/${encodeURIComponent(runId)}/artifacts`),

  getAgentRunEvents: (runId: string) =>
    request<AgentRuntimeEventRecord[]>(`/query/agent-runs/${encodeURIComponent(runId)}/events`),

  getAgentRunTrace: (runId: string) =>
    request<AgentTraceEventRecord[]>(`/query/agent-runs/${encodeURIComponent(runId)}/trace`),
};
