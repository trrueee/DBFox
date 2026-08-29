import type {
  AgentRunStatus,
  RunItemStatus,
} from "../../types/conversation";

const TERMINAL_RUN_STATUSES: ReadonlySet<AgentRunStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);
const FOLLOWABLE_RUN_STATUSES: ReadonlySet<AgentRunStatus> = new Set([
  "created",
  "queued",
  "running",
  "cancelling",
]);
const TERMINAL_ITEM_STATUSES: ReadonlySet<RunItemStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
  "expired",
]);

export const isTerminalRun = (status: AgentRunStatus): boolean =>
  TERMINAL_RUN_STATUSES.has(status);

export const isFollowableRun = (status: AgentRunStatus): boolean =>
  FOLLOWABLE_RUN_STATUSES.has(status);

export const isTerminalRunItem = (status: RunItemStatus): boolean =>
  TERMINAL_ITEM_STATUSES.has(status);
