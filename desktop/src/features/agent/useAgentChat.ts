import { useCallback, useRef, useState } from "react";
import {
  api,
  createAgentRunDraft,
  reduceAgentRuntimeEvent,
} from "../../lib/api";
import type {
  AgentArtifact,
  AgentRunConfig,
  AgentRunDraftState,
  AgentRunResponse,
  AgentRuntimeEvent,
  AgentTaskLens,
  AgentWorkspaceContext,
} from "../../lib/api";

// ── Chat message types ──

export type ChatMessage =
  | UserChatMessage
  | AssistantChatMessage
  | ArtifactChatMessage
  | ActivityChatMessage
  | ApprovalChatMessage
  | ErrorChatMessage;

export interface UserChatMessage {
  role: "user";
  id: string;
  question: string;
  createdAt: number;
}

export interface AssistantChatMessage {
  role: "assistant";
  id: string;
  content: string;
  createdAt: number;
}

export interface ArtifactChatMessage {
  role: "artifact";
  id: string;
  artifact: AgentArtifact;
  createdAt: number;
}

export interface ActivityChatMessage {
  role: "activity";
  id: string;
  label: string;
  steps: ActivityStepState[];
  status: "running" | "completed" | "failed";
  collapsed: boolean;
  contextSummary?: string | null;
  taskLens?: AgentTaskLens | null;
  repairMode?: boolean;
  createdAt: number;
}

export interface ActivityStepState {
  name: string;
  label: string;
  status: "running" | "completed" | "failed";
}

export interface ApprovalChatMessage {
  role: "approval";
  id: string;
  runId: string;
  createdAt: number;
}

export interface ErrorChatMessage {
  role: "error";
  id: string;
  code: string;
  detail: string;
  createdAt: number;
}

export interface UseAgentChatOptions {
  datasourceId: string;
  workspaceContext?: AgentWorkspaceContext | null;
  config?: AgentRunConfig;
  onApplySql?: (sql: string) => void;
  onOpenQueryTab?: (sql: string, title: string) => void;
  onExplainSql?: (sql: string) => void;
}

export interface UseAgentChatReturn {
  messages: ChatMessage[];
  draft: AgentRunDraftState | null;
  isRunning: boolean;
  finalResponse: AgentRunResponse | null;
  error: string | null;
  send: (question: string) => void;
  clear: () => void;
  resumeApproval: (runId: string, approvalId: string) => void;
  rejectApproval: (runId: string, approvalId: string) => void;
}

let _msgSeq = 0;
function nextMsgId(prefix: string): string {
  _msgSeq += 1;
  return `${prefix}-${Date.now()}-${_msgSeq}`;
}

// ── Step display names ──

const STEP_LABELS: Record<string, string> = {
  build_schema_context: "正在理解表结构…",
  build_query_plan: "正在生成查询计划…",
  generate_sql_candidate: "正在生成 SQL…",
  validate_sql: "正在检查 SQL 安全性…",
  execute_sql: "正在执行查询…",
  profile_result: "正在分析结果…",
  suggest_chart: "正在推荐图表…",
  suggest_followups: "正在生成后续建议…",
  answer_synthesizer: "正在整理回答…",
  sql_repair: "正在修复 SQL…",
  planner: "正在重新规划…",
};

function stepLabel(name: string): string {
  return STEP_LABELS[name] || `正在执行 ${name}…`;
}

// ── Hook ──

export function useAgentChat(options: UseAgentChatOptions): UseAgentChatReturn {
  const { datasourceId, workspaceContext, config, onApplySql, onOpenQueryTab } =
    options;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState<AgentRunDraftState | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [finalResponse, setFinalResponse] = useState<AgentRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const msgRef = useRef<ChatMessage[]>([]);
  const draftRef = useRef<AgentRunDraftState | null>(null);

  const append = useCallback((msg: ChatMessage) => {
    msgRef.current = [...msgRef.current, msg];
    setMessages(msgRef.current);
  }, []);

  const updateLastActivity = useCallback(
    (updater: (msg: ActivityChatMessage) => ActivityChatMessage) => {
      const msgs = [...msgRef.current];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "activity") {
          msgs[i] = updater(msgs[i] as ActivityChatMessage);
          msgRef.current = msgs;
          setMessages(msgs);
          return;
        }
      }
    },
    [],
  );

  const send = useCallback(
    (question: string) => {
      if (isRunning) return;

      // Cancel previous
      abortRef.current?.abort();

      const userMsg: UserChatMessage = {
        role: "user",
        id: nextMsgId("user"),
        question,
        createdAt: Date.now(),
      };

      const activityMsg: ActivityChatMessage = {
        role: "activity",
        id: nextMsgId("activity"),
        label: "正在理解问题…",
        steps: [],
        status: "running",
        collapsed: false,
        createdAt: Date.now(),
      };

      msgRef.current = [...msgRef.current, userMsg, activityMsg];
      setMessages(msgRef.current);
      setIsRunning(true);
      setError(null);
      setFinalResponse(null);

      const initialDraft = createAgentRunDraft(question);
      draftRef.current = initialDraft;
      setDraft(initialDraft);

      const controller = new AbortController();
      abortRef.current = controller;

      const onEvent = (event: AgentRuntimeEvent) => {
        if (draftRef.current) {
          draftRef.current = reduceAgentRuntimeEvent(draftRef.current, event);
          setDraft(draftRef.current);
        }
        handleRuntimeEvent(event, {
          append,
          updateLastActivity,
          setFinalResponse,
          setIsRunning,
          setError,
          msgRef,
        });
      };

      api
        .streamAgentQuery(datasourceId, question, {
          ...config,
          workspaceContext: workspaceContext ?? undefined,
        }, {
          signal: controller.signal,
          onEvent,
        })
        .then((response) => {
          setFinalResponse(response);
          // Extract answer text if available
          const answerText = response?.answer?.answer || "";
          if (answerText) {
            const assistantMsg: AssistantChatMessage = {
              role: "assistant",
              id: nextMsgId("assistant"),
              content: answerText,
              createdAt: Date.now(),
            };
            append(assistantMsg);
          }
          // Finalize activity
          updateLastActivity((a) => ({
            ...a,
            status: "completed" as const,
            label: "已完成",
            collapsed: true,
          }));
          setIsRunning(false);
        })
        .catch((err: Error & { code?: string }) => {
          if (err.name === "AbortError") return;
          const errorMsg: ErrorChatMessage = {
            role: "error",
            id: nextMsgId("error"),
            code: err.code || "UNKNOWN",
            detail: err.message || "Agent 请求失败",
            createdAt: Date.now(),
          };
          append(errorMsg);
          updateLastActivity((a) => ({ ...a, status: "failed", label: "请求失败" }));
          setError(err.message);
          setIsRunning(false);
        });
    },
    [datasourceId, workspaceContext, config, isRunning, append, updateLastActivity],
  );

  const clear = useCallback(() => {
    abortRef.current?.abort();
    msgRef.current = [];
    draftRef.current = null;
    setDraft(null);
    setMessages([]);
    setFinalResponse(null);
    setError(null);
    setIsRunning(false);
  }, []);

  const resumeApproval = useCallback(
    (runId: string, approvalId: string) => {
      setIsRunning(true);
      const activityMsg: ActivityChatMessage = {
        role: "activity",
        id: nextMsgId("activity"),
        label: "正在恢复执行…",
        steps: [],
        status: "running",
        collapsed: false,
        createdAt: Date.now(),
      };
      append(activityMsg);

      const resumeDraft = createAgentRunDraft("resume");
      draftRef.current = resumeDraft;
      setDraft(resumeDraft);

      api
        .streamResumeAgentRun(runId, approvalId, {
          onEvent: (event) => {
            if (draftRef.current) {
              draftRef.current = reduceAgentRuntimeEvent(draftRef.current, event);
              setDraft(draftRef.current);
            }
            handleRuntimeEvent(event, {
              append,
              updateLastActivity,
              setFinalResponse,
              setIsRunning,
              setError,
              msgRef,
            });
          },
        })
        .then((response) => {
          setFinalResponse(response);
          const answerText = response?.answer?.answer || "";
          if (answerText) {
            append({
              role: "assistant",
              id: nextMsgId("assistant"),
              content: answerText,
              createdAt: Date.now(),
            });
          }
          updateLastActivity((a) => ({ ...a, status: "completed", label: "已完成", collapsed: true }));
          setIsRunning(false);
        })
        .catch((err: Error & { code?: string }) => {
          append({
            role: "error",
            id: nextMsgId("error"),
            code: err.code || "UNKNOWN",
            detail: err.message,
            createdAt: Date.now(),
          });
          updateLastActivity((a) => ({ ...a, status: "failed", label: "恢复失败" }));
          setIsRunning(false);
        });
    },
    [append, updateLastActivity],
  );

  const rejectApproval = useCallback(
    (runId: string, approvalId: string) => {
      api.rejectAgentApproval(runId, approvalId).catch(() => {});
      setIsRunning(false);
      append({
        role: "error",
        id: nextMsgId("error"),
        code: "APPROVAL_REJECTED",
        detail: "操作已被取消。",
        createdAt: Date.now(),
      });
    },
    [append],
  );

  return {
    messages,
    draft,
    isRunning,
    finalResponse,
    error,
    send,
    clear,
    resumeApproval,
    rejectApproval,
  };
}

// ── Event handler ──

interface EventCtx {
  append: (msg: ChatMessage) => void;
  updateLastActivity: (updater: (msg: ActivityChatMessage) => ActivityChatMessage) => void;
  setFinalResponse: (r: AgentRunResponse | null) => void;
  setIsRunning: (v: boolean) => void;
  setError: (e: string | null) => void;
  msgRef: React.MutableRefObject<ChatMessage[]>;
}

function handleRuntimeEvent(
  event: AgentRuntimeEvent,
  ctx: EventCtx,
) {
  switch (event.type) {
    case "agent.run.started": {
      ctx.updateLastActivity((a) => ({ ...a, label: "正在理解问题…" }));
      break;
    }

    case "agent.context.update": {
      const summary = typeof event.step?.summary === "string" ? event.step.summary : null;
      const repairMode = event.step?.repair_mode === true;
      const rawLens = event.step?.task_lens;
      const taskLens = rawLens && typeof rawLens === "object" && !Array.isArray(rawLens)
        ? {
            goal: typeof rawLens.goal === "string" ? rawLens.goal : undefined,
            current_focus: typeof rawLens.current_focus === "string" ? rawLens.current_focus : undefined,
            next_likely: typeof rawLens.next_likely === "string" ? rawLens.next_likely : undefined,
            missing_evidence: Array.isArray(rawLens.missing_evidence)
              ? rawLens.missing_evidence.filter((v): v is string => typeof v === "string")
              : undefined,
          }
        : undefined;
      if (summary || taskLens) {
        ctx.updateLastActivity((a) => ({
          ...a,
          label: repairMode
            ? "正在修复 SQL…"
            : (taskLens?.current_focus || summary || a.label),
          contextSummary: summary || a.contextSummary,
          taskLens: taskLens || a.taskLens,
          repairMode: repairMode || a.repairMode,
        }));
      }
      break;
    }

    case "agent.progress.update": {
      const step = event.step || {};
      const name = typeof step.name === "string" ? step.name : "progress";
      const summary = typeof step.summary === "string" ? step.summary : "";
      const stepStatus = step.status === "failed"
        ? "failed" as const
        : step.status === "completed"
          ? "completed" as const
          : "running" as const;
      const label = summary || stepLabel(name);
      ctx.updateLastActivity((a) => {
        const existing = a.steps.find((s) => s.name === name);
        const nextSteps = existing
          ? a.steps.map((s) => (s.name === name ? { ...s, label, status: stepStatus } : s))
          : [...a.steps, { name, label, status: stepStatus }];
        return {
          ...a,
          label: stepStatus === "running" ? label : a.label,
          repairMode: name === "sql_repair" || a.repairMode,
          steps: nextSteps,
        };
      });
      break;
    }

    case "agent.step.started": {
      const name = typeof event.step?.name === "string" ? event.step.name : "";
      ctx.updateLastActivity((a) => {
        const existing = a.steps.find((s) => s.name === name);
        if (existing) {
          return {
            ...a,
            label: stepLabel(name),
            steps: a.steps.map((s) => (s.name === name ? { ...s, status: "running" as const } : s)),
          };
        }
        return {
          ...a,
          label: stepLabel(name),
          steps: [
            ...a.steps,
            { name, label: stepLabel(name), status: "running" as const },
          ],
        };
      });
      break;
    }

    case "agent.step.completed": {
      const name = typeof event.step?.name === "string" ? event.step.name : "";
      const failed = event.step?.status === "failed";
      ctx.updateLastActivity((a) => ({
        ...a,
        label: failed ? `步骤失败: ${stepLabel(name)}` : stepLabel(name),
        steps: a.steps.map((s) =>
          s.name === name
            ? { ...s, status: (failed ? "failed" : "completed") as const }
            : s,
        ),
      }));
      break;
    }

    case "agent.artifact.created": {
      if (event.artifact) {
        ctx.append({
          role: "artifact",
          id: nextMsgId("artifact"),
          artifact: event.artifact,
          createdAt: Date.now(),
        });
      }
      break;
    }

    case "agent.approval.required": {
      ctx.append({
        role: "approval",
        id: nextMsgId("approval"),
        runId: event.run_id || "",
        createdAt: Date.now(),
      });
      break;
    }

    case "agent.answer.completed": {
      if (event.answer?.answer) {
        ctx.append({
          role: "assistant",
          id: nextMsgId("assistant"),
          content: event.answer.answer,
          createdAt: Date.now(),
        });
      }
      break;
    }

    case "agent.run.completed": {
      if (event.response?.answer?.answer) {
        ctx.append({
          role: "assistant",
          id: nextMsgId("assistant"),
          content: event.response.answer.answer,
          createdAt: Date.now(),
        });
      }
      ctx.updateLastActivity((a) => ({
        ...a,
        status: "completed",
        label: "已完成",
        collapsed: true,
      }));
      ctx.setIsRunning(false);
      break;
    }

    case "agent.run.failed": {
      const detail = event.error || event.response?.error || "Agent 运行失败";
      ctx.append({
        role: "error",
        id: nextMsgId("error"),
        code: (event as Record<string, unknown>).code as string || "AGENT_ERROR",
        detail,
        createdAt: Date.now(),
      });
      ctx.updateLastActivity((a) => ({
        ...a,
        status: "failed",
        label: "请求失败",
      }));
      ctx.setIsRunning(false);
      break;
    }

    default:
      break;
  }
}
