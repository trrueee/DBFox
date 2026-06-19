import type { AgentTimelineItem } from "../workspace/agentTimeline";
import type { AgentAnswer, FollowUpSuggestion } from "../../lib/api/types";
import type { AgentTabStatus, AgentApprovalInfo, WorkspaceTab } from "../../mock/dbfoxMock";
import type { AgentArtifact } from "../../types/agentArtifact";

// ---------------------------------------------------------------------------
// Agent Task View — feature-scoped types
// ---------------------------------------------------------------------------

/** One turn in a multi-turn agent conversation. */
export interface ConversationTurn {
  id: string;
  userMessage: string;
  userTimestamp?: number;
  /** Plain-text AI response (for history turns without agent trace data). */
  aiText?: string;
  /** Whether this turn has agent execution trace data. */
  hasAgentData: boolean;
  agentTimeline?: AgentTimelineItem[];
  agentAnswer?: AgentAnswer | null;
  agentStatus?: AgentTabStatus | "idle";
  artifacts?: AgentArtifact[];
  suggestions?: FollowUpSuggestion[] | null;
  approval?: AgentApprovalInfo | null;
}

/** Internal task step — maps timeline items to renderable task steps. */
export interface AgentTaskStep {
  id: string;
  type: "thinking" | "tool_call" | "assistant" | "user";
  status: "idle" | "running" | "success" | "failed" | "skipped" | "info";
  title: string;
  subtitle?: string;
  content: string;
  toolName?: string;
  toolIcon?: string;
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: string | null;
  latencyMs?: number | null;
  /** Timestamp when this step entered its current status (ms since epoch). */
  timestamp: number;
}

/** Compact data required by a tool-call card. */
export interface ToolCallData {
  toolName: string;
  title: string;
  subtitle?: string;
  status: "running" | "success" | "failed" | "skipped";
  input?: Record<string, unknown> | null;
  output?: Record<string, unknown> | null;
  error?: string | null;
  latencyMs?: number | null;
}

/** Compact data required by a thinking-step row. */
export interface ThinkingData {
  content: string;
  status: "idle" | "running" | "info";
}

/** Summary computed from completed timeline items. */
export interface AgentTaskSummary {
  totalSteps: number;
  toolCount: number;
  queryCount: number;
  rowCount: number | null;
  totalLatencyMs: number | null;
}

/** Runtime view-model for the agent task feature. */
export interface AgentTaskState {
  steps: AgentTaskStep[];
  status: AgentTabStatus | "idle";
  finalAnswer: AgentAnswer | null;
  summary: AgentTaskSummary | null;
  error: string | null;
  queryText: string;
  createdAt: number;
}

/** Actions dispatched to the useAgentTask reducer. */
export type AgentTaskAction =
  | { type: "ADD_THINKING_STEP"; payload: { id: string; title: string; content: string; status: "running" | "info"; timestamp: number } }
  | { type: "ADD_TOOL_CALL_STEP"; payload: { id: string; toolName: string; title: string; subtitle?: string; input?: Record<string, unknown> | null; timestamp: number } }
  | { type: "UPDATE_STEP"; payload: { id: string; patch: Partial<Pick<AgentTaskStep, "status" | "content" | "output" | "error" | "latencyMs" | "toolName" | "title" | "subtitle">> } }
  | { type: "COMPLETE_TASK"; payload: { finalAnswer: AgentAnswer | null; error: string | null } }
  | { type: "FAIL_TASK"; payload: { error: string } }
  | { type: "SET_STATUS"; payload: { status: AgentTabStatus | "idle" } }
  | { type: "CLEAR" };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function mapTimelineItemToTaskStep(item: AgentTimelineItem, index: number): AgentTaskStep {
  const kind: AgentTaskStep["type"] =
    item.kind === "assistant" ? "thinking" : item.kind === "tool" ? "tool_call" : "user";

  return {
    id: item.id || `step-${index}`,
    type: kind,
    status: item.status as AgentTaskStep["status"],
    title: item.title || "Step",
    subtitle: item.subtitle,
    content: item.content || "",
    toolName: item.toolName,
    input: item.input ?? null,
    output: item.output ?? null,
    error: item.error ?? null,
    latencyMs: item.latencyMs ?? null,
    timestamp: Date.now(),
  };
}

export function computeSummary(steps: AgentTaskStep[]): AgentTaskSummary {
  let toolCount = 0;
  let queryCount = 0;
  let rowCount: number | null = null;
  let totalLatencyMs: number | null = null;

  for (const step of steps) {
    if (step.type !== "tool_call") continue;
    toolCount++;

    if (step.toolName && /^(db\.query|query_database|execute_sql)$/i.test(step.toolName)) {
      queryCount++;
    }

    if (typeof step.latencyMs === "number" && step.latencyMs > 0) {
      totalLatencyMs = (totalLatencyMs ?? 0) + step.latencyMs;
    }

    if (step.output) {
      const output = step.output;
      const rows =
        (typeof output.returned_rows === "number" ? output.returned_rows : undefined) ??
        (typeof output.rowCount === "number" ? output.rowCount : undefined) ??
        (Array.isArray(output.rows) ? output.rows.length : undefined);
      if (typeof rows === "number" && (rowCount === null || rows > rowCount)) {
        rowCount = rows;
      }
    }
  }

  return {
    totalSteps: steps.length,
    toolCount,
    queryCount: queryCount > 0 ? queryCount : (toolCount > 0 ? 1 : 0),
    rowCount,
    totalLatencyMs,
  };
}

export const STATUS_LABELS: Record<string, string> = {
  idle: "等待开始",
  running: "分析中",
  waiting_approval: "等待审批",
  completed: "已完成",
  failed: "运行失败",
};

export const RISK_LABELS: Record<string, string> = {
  safe: "低风险",
  warning: "需要确认",
  danger: "高风险",
};

// ---------------------------------------------------------------------------
// Conversation parsing
// ---------------------------------------------------------------------------

/** Group chatMessages + agentTimeline into per-turn conversation turns.
 *  Each turn = one user message + its corresponding AI response (trace + answer).
 *  History turns get plain AI text; the most recent turn gets full agent trace data.
 *
 *  IMPORTANT: agent data (timeline, answer, artifacts) must be attached to the
 *  turn that contains the user's question, NOT to orphan AI-only turns created
 *  by trailing messages like suggestions. */
export function parseConversationTurns(tab: WorkspaceTab): ConversationTurn[] {
  const messages = tab.chatMessages || [];
  const timeline = tab.agentTimeline || [];
  const turns: ConversationTurn[] = [];
  let pendingUser: { text: string; id: number } | null = null;

  for (const msg of messages) {
    if (msg.sender === "user") {
      if (pendingUser) {
        // Previous user had no AI response — record as incomplete turn
        turns.push({
          id: `turn-${pendingUser.id}`,
          userMessage: pendingUser.text,
          userTimestamp: pendingUser.id,
          hasAgentData: false,
        });
      }
      pendingUser = { text: msg.text, id: msg.id };
    } else if (msg.sender === "ai") {
      if (pendingUser) {
        turns.push({
          id: `turn-${pendingUser.id}`,
          userMessage: pendingUser.text,
          userTimestamp: pendingUser.id,
          aiText: msg.text,
          hasAgentData: false,
        });
        pendingUser = null;
      } else if (turns.length > 0) {
        // AI message without preceding user (e.g. suggestions appended after
        // the answer) — merge into the previous turn rather than creating an
        // orphan turn that would steal agent data.
        const last = turns[turns.length - 1];
        last.aiText = last.aiText
          ? `${last.aiText}\n\n${msg.text}`
          : msg.text;
      }
      // If there are no turns at all, drop the orphan — nothing to attach to.
    }
  }

  // Determine where agent data belongs
  const hasTimeline = timeline.length > 0;
  const agentStatus = tab.agentStatus;

  if (pendingUser) {
    // Last user message has no AI text yet — agent is (or was) working on it
    turns.push({
      id: `turn-${pendingUser.id}`,
      userMessage: pendingUser.text,
      userTimestamp: pendingUser.id,
      hasAgentData: hasTimeline || !!agentStatus,
      agentTimeline: hasTimeline ? timeline : undefined,
      agentAnswer: tab.agentAnswer,
      agentStatus: agentStatus || "idle",
      artifacts: tab.artifacts,
      suggestions: tab.agentSuggestions,
      approval: tab.agentApproval,
    });
  } else if (hasTimeline && turns.length > 0) {
    // Find the LAST turn that has a real user message, so agent data
    // (timeline, answer, artifacts) is never attached to an orphan AI-only
    // turn created by trailing suggestions or progress messages.
    let targetTurn: ConversationTurn | null = null;
    for (let i = turns.length - 1; i >= 0; i--) {
      if (turns[i].userMessage) {
        targetTurn = turns[i];
        break;
      }
    }
    if (!targetTurn) {
      targetTurn = turns[turns.length - 1];
    }
    targetTurn.hasAgentData = true;
    targetTurn.agentTimeline = timeline;
    targetTurn.agentAnswer = tab.agentAnswer;
    targetTurn.agentStatus = agentStatus || "idle";
    targetTurn.artifacts = tab.artifacts;
    targetTurn.suggestions = tab.agentSuggestions;
    targetTurn.approval = tab.agentApproval;
  } else if (hasTimeline && turns.length === 0) {
    // Timeline items exist but no chat messages (edge case) — build single turn
    const userItem = timeline.find((t) => t.kind === "user");
    turns.push({
      id: "turn-timeline-only",
      userMessage: userItem?.content || tab.queryText || "",
      hasAgentData: true,
      agentTimeline: timeline,
      agentAnswer: tab.agentAnswer,
      agentStatus: agentStatus || "idle",
      artifacts: tab.artifacts,
      suggestions: tab.agentSuggestions,
      approval: tab.agentApproval,
    });
  }

  return turns;
}
