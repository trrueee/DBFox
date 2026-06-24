/** Core workspace types. */

import type { AgentArtifact, ResultViewArtifact } from "./agentArtifact";
import type { AgentTimelineItem } from "../features/workspace/agentTimeline";
import type { AgentAnswer, FollowUpSuggestion } from "../lib/api/types";

export type WorkspaceTabType =
  | "smart-query"
  | "table"
  | "sql"
  | "multi-table"
  | "query-result"
  | "artifact-result"
  | "conversation-history"
  | "llm-config"
  | "datasource-settings"
  | "agent-eval"
  | "diagnostics";

export type AgentApprovalInfo = {
  runId: string;
  approvalId: string;
  stepName: string;
  riskLevel: string;
  reason?: string;
  sql?: string;
};

export type AgentTabStatus = "running" | "waiting_approval" | "completed" | "failed";

export interface WorkspaceTab {
  id: string;
  title: string;
  type: WorkspaceTabType;
  tableId?: string;
  datasourceId?: string;
  datasourceDbType?: string | null;
  selectedTables?: string[];
  queryText?: string;
  conversationId?: string;
  // Conversation content is stored in conversationStore. These fields are temporary compatibility state for older agent store tests.
  chatMessages?: { id: number; sender: "user" | "ai"; text: string }[];
  agentTimeline?: AgentTimelineItem[];
  artifacts?: AgentArtifact[];
  artifactResult?: ResultViewArtifact;
  agentRunId?: string;
  agentSessionId?: string;
  agentStatus?: AgentTabStatus;
  agentApproval?: AgentApprovalInfo | null;
  agentAnswer?: AgentAnswer | null;
  agentSuggestions?: FollowUpSuggestion[] | null;
}

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  type: "database" | "schema" | "table" | "multi-table";
  targetNode: string;
}
