import {
  CheckCircleIcon, CircleIcon, CircleNotchIcon, ClockIcon, QuestionIcon,
  ShieldWarningIcon, StopCircleIcon, WarningCircleIcon,
} from "@/components/icons";
import type { AgentRunStatus, ConversationDetail, ConversationSummary } from "../../types/conversation";
import { isTerminalRun } from "./conversationState";

/** Presentation of server-observed run state, never a prediction from sending or animation. */
const PRESENTATION = {
  idle: { label: "尚未运行", icon: CircleIcon, tone: "quiet", priority: 2 },
  created: { label: "准备中", icon: ClockIcon, tone: "quiet", priority: 1 },
  queued: { label: "排队中", icon: ClockIcon, tone: "quiet", priority: 1 },
  running: { label: "运行中", icon: CircleNotchIcon, tone: "active", priority: 1 },
  waiting_approval: { label: "等待审批", icon: ShieldWarningIcon, tone: "attention", priority: 0 },
  waiting_input: { label: "等待答复", icon: QuestionIcon, tone: "attention", priority: 0 },
  cancelling: { label: "正在停止", icon: StopCircleIcon, tone: "quiet", priority: 1 },
  cancelled: { label: "已停止", icon: StopCircleIcon, tone: "quiet", priority: 2 },
  // A completed run can have a bounded partial result; do not imply task success.
  completed: { label: "本轮已结束", icon: CheckCircleIcon, tone: "quiet", priority: 2 },
  failed: { label: "运行失败", icon: WarningCircleIcon, tone: "danger", priority: 2 },
} as const satisfies Record<AgentRunStatus | "idle", { label: string; icon: typeof CircleIcon; tone: string; priority: number }>;

export function runPresentation(status?: AgentRunStatus | null) {
  return PRESENTATION[status ?? "idle"];
}

/** Both projections use the same durable session cursor, including across Run changes. */
export function threadRunStatus(detail: Pick<ConversationDetail, "runs" | "cursor"> | undefined, summary?: Pick<ConversationSummary, "run_status" | "cursor">): AgentRunStatus | null {
  // The index includes all Runs, even when the snapshot's history is paginated.
  if (summary?.cursor !== undefined && (!detail || summary.cursor >= (detail.cursor ?? 0))) return summary.run_status ?? null;
  if (detail) return detail.runs.find(run => !isTerminalRun(run.status))?.status ?? detail.runs.at(-1)?.status ?? null;
  return summary?.run_status ?? null;
}
