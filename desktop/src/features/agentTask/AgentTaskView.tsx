import { useEffect, useState, useRef, useMemo } from "react";
import { Loader2, XCircle, ShieldAlert } from "lucide-react";
import "./AgentTaskView.css";
import type { WorkspaceTab } from "../../mock/databoxMock";
import { AgentTurnItem } from "./AgentTurnItem";
import { parseConversationTurns, RISK_LABELS } from "./types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AgentTaskViewProps {
  tab: WorkspaceTab;
  onCancel: (tabId: string) => void;
  onRegenerate: (tabId: string) => void;
  onApproveAgent: (tabId: string) => void;
  onRejectAgent: (tabId: string) => void;
  onSendFollowUp: (tabId: string, text: string) => void;
  onOpenSqlConsole: (initialSql?: string) => void;
  onToast: (message: string) => void;
}

// ---------------------------------------------------------------------------
// Approval card (shown inline within the conversation for the current turn)
// ---------------------------------------------------------------------------

function AgentApprovalCard({
  approval,
  onApprove,
  onReject,
}: {
  approval: NonNullable<WorkspaceTab["agentApproval"]>;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <div className={`task-approval-card ${approval.riskLevel === "danger" ? "task-approval-danger" : ""}`}>
      <div className="task-approval-head">
        <ShieldAlert size={14} className="text-amber-500" />
        <span className="task-approval-title">执行前需要你的确认</span>
        <span className={`task-approval-risk task-approval-risk-${approval.riskLevel}`}>
          {RISK_LABELS[approval.riskLevel] || approval.riskLevel}
        </span>
      </div>
      {approval.reason && <div className="task-approval-reason">{approval.reason}</div>}
      {approval.sql && <pre className="task-approval-sql">{approval.sql}</pre>}
      <div className="task-approval-actions">
        <button className="task-approval-btn task-approval-approve" onClick={onApprove} type="button">
          批准并继续
        </button>
        <button className="task-approval-btn task-approval-reject" onClick={onReject} type="button">
          拒绝
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component — multi-turn conversation container
// ---------------------------------------------------------------------------

export function AgentTaskView({
  tab,
  onCancel,
  onApproveAgent,
  onRejectAgent,
  onSendFollowUp,
  onOpenSqlConsole,
  onToast,
}: AgentTaskViewProps) {
  // ── Parse conversation ──
  const turns = useMemo(() => parseConversationTurns(tab), [
    tab.chatMessages,
    tab.agentTimeline,
    tab.agentAnswer,
    tab.agentStatus,
    tab.artifacts,
    tab.agentSuggestions,
    tab.agentApproval,
    tab.queryText,
  ]);

  // ── Current agent state ──
  const agentStatus = tab.agentStatus || "idle";
  const isRunning = agentStatus === "running" || agentStatus === "waiting_approval";
  const isDone = agentStatus === "completed" || agentStatus === "failed";
  const approval = tab.agentApproval;

  // ── Elapsed timer ──
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isRunning) {
      setElapsedSeconds(0);
      elapsedRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 0.2);
      }, 200);
    } else {
      if (elapsedRef.current) {
        clearInterval(elapsedRef.current);
        elapsedRef.current = null;
      }
    }
    return () => {
      if (elapsedRef.current) {
        clearInterval(elapsedRef.current);
        elapsedRef.current = null;
      }
    };
  }, [isRunning, tab.agentRunId]);

  const formattedElapsed = useMemo(() => {
    const totalSec = Math.floor(elapsedSeconds);
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  }, [elapsedSeconds]);

  // ── Auto-scroll conversation body during running ──
  const bodyRef = useRef<HTMLDivElement>(null);
  const timelineLen = tab.agentTimeline?.length || 0;
  const prevLenRef = useRef(timelineLen);
  useEffect(() => {
    if (isRunning && timelineLen > prevLenRef.current && bodyRef.current) {
      bodyRef.current.scrollTo({
        top: bodyRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
    prevLenRef.current = timelineLen;
  }, [isRunning, timelineLen]);

  // ── Render ──

  // Empty state
  if (turns.length === 0 && agentStatus === "idle") {
    return (
      <div className="agent-task-view">
        <div className="task-empty-state">
          <div className="task-empty-scan-line" />
          <p className="task-empty-text">准备开始分析…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-task-view">
      {/* ── Header ── */}
      <div className="task-header">
        <div className="task-header-left">
          <span className={`task-status-badge task-status-${agentStatus}`}>
            {agentStatus === "running"
              ? "分析中"
              : agentStatus === "waiting_approval"
                ? "等待审批"
                : agentStatus === "completed"
                  ? "已完成"
                  : agentStatus === "failed"
                    ? "失败"
                    : "就绪"}
          </span>
          {isRunning && (
            <span className="task-header-elapsed">
              <Loader2 size={10} className="animate-spin" />
              {formattedElapsed}
            </span>
          )}
        </div>
        <div className="task-header-actions">
          {isRunning && (
            <button
              className="task-header-cancel-btn"
              onClick={() => onCancel(tab.id)}
              type="button"
              title="取消运行"
            >
              <XCircle size={13} />
              <span>取消</span>
            </button>
          )}
        </div>
      </div>

      {/* ── Conversation body ── */}
      <div className="task-scroll-body" ref={bodyRef}>
        {/* Conversation turns */}
        {turns.map((turn, index) => (
          <AgentTurnItem
            key={turn.id}
            turn={turn}
            isLast={index === turns.length - 1}
            onOpenSqlConsole={onOpenSqlConsole}
            onSendFollowUp={(text) => onSendFollowUp(tab.id, text)}
            onToast={onToast}
          />
        ))}

        {/* Approval card (shown between turns and footer) */}
        {approval && (
          <AgentApprovalCard
            approval={approval}
            onApprove={() => onApproveAgent(tab.id)}
            onReject={() => onRejectAgent(tab.id)}
          />
        )}
      </div>

      {/* ── Footer: Follow-up input ── */}
      {isDone && (
        <div className="task-footer">
          <div className="task-chat-input-wrapper">
            <input
              type="text"
              className="task-chat-input"
              placeholder="继续提问…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.currentTarget.value.trim()) {
                  onSendFollowUp(tab.id, e.currentTarget.value.trim());
                  e.currentTarget.value = "";
                }
              }}
            />
            <button
              className="task-chat-send-btn"
              onClick={(e) => {
                const input = e.currentTarget.parentElement?.querySelector("input") as HTMLInputElement;
                if (input?.value.trim()) {
                  onSendFollowUp(tab.id, input.value.trim());
                  input.value = "";
                }
              }}
              type="button"
              aria-label="发送追问"
            >
              <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
