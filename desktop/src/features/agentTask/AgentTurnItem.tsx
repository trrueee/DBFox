import { useEffect, useState, useRef, useMemo } from "react";
import { Loader2 } from "lucide-react";
import type { ConversationTurn, AgentTaskSummary } from "./types";
import { computeSummary } from "./types";
import { UserPromptCard } from "./UserPromptCard";
import { TraceTimeline } from "./TraceTimeline";
import { TraceSummaryBar } from "./TraceSummaryBar";
import { FinalAnswerCard } from "./FinalAnswerCard";
import { EVIDENCE_ARTIFACT_TYPES } from "../../lib/api/types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AgentTurnItemProps {
  turn: ConversationTurn;
  isLast: boolean;
  onOpenSqlConsole: (initialSql?: string) => void;
  onSendFollowUp: (text: string) => void;
  onToast: (message: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgentTurnItem({
  turn,
  isLast,
  onOpenSqlConsole,
  onSendFollowUp,
  onToast,
}: AgentTurnItemProps) {
  const hasAgent = turn.hasAgentData;
  const agentStatus = turn.agentStatus || "idle";
  const isRunning = agentStatus === "running" || agentStatus === "waiting_approval";
  const isDone = agentStatus === "completed" || agentStatus === "failed";
  const isFailed = agentStatus === "failed";
  const hasAnswer = !!turn.agentAnswer?.answer;
  const timeline = useMemo(() => turn.agentTimeline || [], [turn.agentTimeline]);

  // Per-turn trace expand state
  const [traceExpanded, setTraceExpanded] = useState(
    isRunning || (isFailed && isLast),
  );
  const collapseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wasRunningRef = useRef(isRunning);

  // Per-turn summary
  const summary: AgentTaskSummary = useMemo(() => {
    if (!hasAgent || timeline.length === 0) {
      return { totalSteps: 0, toolCount: 0, queryCount: 0, rowCount: null, totalLatencyMs: null };
    }
    const steps = timeline.map((item, i) => ({
      id: item.id || `s-${i}`,
      type: item.kind === "assistant" ? "thinking" as const : item.kind === "tool" ? "tool_call" as const : "user" as const,
      status: item.status,
      title: item.title || "",
      content: item.content || "",
      toolName: item.toolName,
      input: item.input,
      output: item.output,
      error: item.error,
      latencyMs: item.latencyMs,
      timestamp: 0,
    }));
    return computeSummary(steps);
  }, [hasAgent, timeline]);

  // Auto-collapse once when the active last turn finishes.
  useEffect(() => {
    const justFinishedRunning = wasRunningRef.current && !isRunning;

    if (isLast && justFinishedRunning && isDone && hasAnswer && traceExpanded) {
      collapseTimerRef.current = setTimeout(() => {
        setTraceExpanded(false);
      }, 600);
    }
    // Expand on start
    if (isLast && isRunning && !traceExpanded) {
      setTraceExpanded(true);
    }
    wasRunningRef.current = isRunning;
    return () => {
      if (collapseTimerRef.current) {
        clearTimeout(collapseTimerRef.current);
        collapseTimerRef.current = null;
      }
    };
  }, [isLast, isDone, hasAnswer, isRunning, traceExpanded]);

  // Auto-scroll for running turn
  const traceBodyRef = useRef<HTMLDivElement>(null);
  const prevLenRef = useRef(timeline.length);
  useEffect(() => {
    if (isLast && isRunning && timeline.length > prevLenRef.current && traceBodyRef.current) {
      traceBodyRef.current.scrollTo({
        top: traceBodyRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
    prevLenRef.current = timeline.length;
  }, [isLast, isRunning, timeline.length]);

  // ── Render ──

  return (
    <div className={`task-turn ${isLast ? "task-turn-last" : ""} ${isRunning ? "task-turn-active" : ""}`}>
      {/* ── User side ── */}
      {turn.userMessage && (
        <UserPromptCard
          queryText={turn.userMessage}
          createdAt={turn.userTimestamp}
        />
      )}

      {/* ── AI side ── */}
      <div className="task-turn-ai">

        {/* ── Agent trace section (only for turns with agent data) ── */}
        {hasAgent && timeline.length > 0 && (
          <div className="task-turn-trace">
            {traceExpanded ? (
              <div className="task-turn-trace-body" ref={traceBodyRef}>
                <TraceTimeline
                  items={timeline}
                  isRunning={isRunning && isLast}
                />
                {isDone && (
                  <button
                    className="task-trace-collapse-btn"
                    onClick={() => setTraceExpanded(false)}
                    type="button"
                  >
                    收起思考过程
                  </button>
                )}
              </div>
            ) : (
              <TraceSummaryBar
                summary={summary}
                status={agentStatus}
                expanded={false}
                onToggle={() => setTraceExpanded(true)}
              />
            )}
          </div>
        )}

        {/* Running indicator with cancel (for current turn, when running but no timeline yet) */}
        {hasAgent && isRunning && isLast && timeline.length === 0 && (
          <div className="task-turn-ai-starting">
            <Loader2 size={12} className="animate-spin text-indigo-500" />
            <span>AI 正在分析你的问题…</span>
          </div>
        )}

        {/* ── Final answer (for turns with agent answer) ── */}
        {hasAgent && hasAnswer && turn.agentAnswer && (
          <FinalAnswerCard
            answer={turn.agentAnswer}
            artifacts={(turn.artifacts || []).filter(a => EVIDENCE_ARTIFACT_TYPES.has(a.type))}
            agentStatus={agentStatus}
            onSendFollowUp={onSendFollowUp}
            onOpenSqlConsole={onOpenSqlConsole}
            onToast={onToast}
          />
        )}

        {/* Failed banner for current turn */}
        {hasAgent && isFailed && isLast && !hasAnswer && (
          <div className="task-turn-ai-failed">
            <div className="task-failed-banner-inline">
              <span className="task-failed-banner-inline-title">Agent 未能完成分析</span>
              {turn.agentAnswer?.answer && (
                <span className="task-failed-banner-inline-msg">
                  {turn.agentAnswer.answer}
                </span>
              )}
            </div>
          </div>
        )}

        {/* ── Plain AI text (for history turns without agent data) ── */}
        {!hasAgent && turn.aiText && (
          <div className="task-turn-ai-text">
            <span>{turn.aiText}</span>
          </div>
        )}
      </div>
    </div>
  );
}
