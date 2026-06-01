import type { AgentArtifact, AgentFollowUpContext, AgentRunResponse } from "./types";

const MAX_SUMMARY_LENGTH = 420;

export function buildAgentFollowUpContext(result: AgentRunResponse): AgentFollowUpContext {
  return {
    session_id: result.session_id,
    parent_run_id: result.run_id,
    previous_question: result.question,
    previous_answer: result.answer?.answer || result.explanation || null,
    artifacts: (result.artifacts || []).slice(0, 8).map((artifact) => ({
      id: artifact.id,
      type: artifact.type,
      title: artifact.title,
      summary: summarizeArtifact(artifact),
      payload: compactPayload(artifact),
    })),
  };
}

function summarizeArtifact(artifact: AgentArtifact): string {
  if (artifact.type === "sql" && typeof artifact.payload.sql === "string") {
    return compactText(artifact.payload.sql);
  }
  if (artifact.type === "table") {
    const columns = Array.isArray(artifact.payload.columns) ? artifact.payload.columns.map(String) : [];
    return compactText(`rowCount=${artifact.payload.rowCount ?? 0}; columns=${columns.slice(0, 8).join(", ")}`);
  }
  if (artifact.type === "insight") {
    const facts = Array.isArray(artifact.payload.notable_facts) ? artifact.payload.notable_facts.map(String) : [];
    const patterns = Array.isArray(artifact.payload.detected_patterns) ? artifact.payload.detected_patterns.map(String) : [];
    return compactText(`patterns=${patterns.join(", ")}; facts=${facts.slice(0, 4).join("; ")}`);
  }
  if (artifact.type === "safety") {
    return compactText(`can_execute=${artifact.payload.can_execute}; messages=${JSON.stringify(artifact.payload.messages || [])}`);
  }
  if (artifact.type === "error") {
    return compactText(String(artifact.payload.error || "Agent stopped."));
  }
  return compactText(JSON.stringify(artifact.payload));
}

function compactPayload(artifact: AgentArtifact): Record<string, unknown> {
  if (artifact.type === "sql") return { sql: artifact.payload.sql };
  if (artifact.type === "table") {
    return {
      columns: artifact.payload.columns,
      rowCount: artifact.payload.rowCount,
    };
  }
  if (artifact.type === "insight") {
    return {
      row_count: artifact.payload.row_count,
      detected_patterns: artifact.payload.detected_patterns,
      notable_facts: artifact.payload.notable_facts,
      limitations: artifact.payload.limitations,
    };
  }
  if (artifact.type === "safety") {
    return {
      can_execute: artifact.payload.can_execute,
      requires_confirmation: artifact.payload.requires_confirmation,
      messages: artifact.payload.messages,
    };
  }
  return {};
}

function compactText(value: string): string {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= MAX_SUMMARY_LENGTH) return text;
  return `${text.slice(0, MAX_SUMMARY_LENGTH - 3).trimEnd()}...`;
}
