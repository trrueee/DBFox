import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3, Layers, Loader2, ShieldAlert, Sparkles, User } from "lucide-react";
import { useMemo, useState } from "react";
import type { AgentApprovalInfo, WorkspaceTab } from "../../../mock/databoxMock";
import { ArtifactRenderer } from "../artifacts/ArtifactRenderer";
import { AnswerCard } from "./AnswerCard";
import { FollowUpChips } from "./FollowUpChips";
import { QueryMessages } from "./QueryMessages";
import "./AgentConversationThread.css";

type QueryMessage = NonNullable<WorkspaceTab["chatMessages"]>[number];

type MessagePart =
  | { id: string; type: "text"; text: string }
  | { id: string; type: "approval"; approval: AgentApprovalInfo }
  | { id: string; type: "artifacts" }
  | { id: string; type: "answer" }
  | { id: string; type: "suggestions" }
  | { id: string; type: "error"; text: string };

interface AgentConversationThreadProps {
  tab: WorkspaceTab;
  onOpenSqlConsole: () => void;
  onSetSqlQuery: (sql: string) => void;
  onSendFollowUp: (tabId: string, text: string) => void;
  onApproveAgent: (tabId: string) => void;
  onRejectAgent: (tabId: string) => void;
  onToast: (message: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  running: "分析中",
  waiting_approval: "等待确认",
  completed: "已完成",
  failed: "已停止",
};

const RISK_LABELS: Record<string, string> = {
  safe: "低风险",
  warning: "需要确认",
  danger: "高风险",
};

export function AgentConversationThread(props: AgentConversationThreadProps) {
  const { tab } = props;
  const [showRawMessages, setShowRawMessages] = useState(false);
  const messages = useMemo(() => normalizeMessages(tab), [tab]);
  const lastAssistantId = [...messages].reverse().find((message) => message.sender === "ai")?.id;

  return (
    <div className="agent-thread">
      {messages.map((message) => {
        if (message.sender === "user") return <UserTurn key={message.id} message={message} />;
        if (message.id !== lastAssistantId) return <AssistantTextTurn key={message.id} message={message} />;
        return <AssistantRunTurn key={message.id} {...props} message={message} />;
      })}

      {messages.every((message) => message.sender !== "ai") && <AssistantRunTurn {...props} />}

      {(tab.chatMessages?.length ?? 0) > 1 && (
        <div className="agent-raw-messages">
          <button className="agent-raw-toggle" onClick={() => setShowRawMessages((value) => !value)}>
            {showRawMessages ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <span>原始消息流</span>
            <strong>{tab.chatMessages?.length ?? 0}</strong>
          </button>
          {showRawMessages && (
            <div className="agent-raw-body">
              <QueryMessages messages={tab.chatMessages || []} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function normalizeMessages(tab: WorkspaceTab): QueryMessage[] {
  if (tab.chatMessages?.length) return tab.chatMessages;
  if (tab.queryText?.trim()) return [{ id: -1, sender: "user", text: tab.queryText.trim() }];
  return [];
}

function UserTurn({ message }: { message: QueryMessage }) {
  return (
    <div className="agent-turn agent-turn-user">
      <div className="agent-avatar agent-avatar-user"><User size={13} /></div>
      <div className="agent-user-bubble">{message.text}</div>
    </div>
  );
}

function AssistantTextTurn({ message }: { message: QueryMessage }) {
  return (
    <div className="agent-turn agent-turn-assistant">
      <div className="agent-avatar agent-avatar-ai"><Sparkles size={13} /></div>
      <div className="agent-assistant-bubble agent-assistant-text-only">{message.text}</div>
    </div>
  );
}

function AssistantRunTurn(props: AgentConversationThreadProps & { message?: QueryMessage }) {
  const { tab } = props;
  const isRunning = tab.agentStatus === "running";
  const parts = buildMessageParts(tab, props.message);

  return (
    <div className="agent-turn agent-turn-assistant">
      <div className="agent-avatar agent-avatar-ai">
        {isRunning ? <Loader2 size={13} className="agent-spin" /> : <Sparkles size={13} />}
      </div>
      <div className="agent-assistant-bubble">
        <div className="agent-run-head">
          <div className="agent-run-title"><Sparkles size={13} /><span>DataBox Agent</span></div>
          <span className={`agent-status-pill agent-status-${tab.agentStatus || "running"}`}>
            {isRunning && <Loader2 size={10} className="agent-spin" />}
            {tab.agentStatus ? STATUS_LABELS[tab.agentStatus] || tab.agentStatus : "准备中"}
          </span>
        </div>

        {parts.map((part) => <MessagePartRenderer key={part.id} part={part} {...props} />)}
      </div>
    </div>
  );
}

function MessagePartRenderer(props: AgentConversationThreadProps & { part: MessagePart }) {
  const { part, tab } = props;

  if (part.type === "text") return <AgentNarration text={part.text} running={tab.agentStatus === "running"} />;
  if (part.type === "approval") return <AgentApprovalCard tabId={tab.id} approval={part.approval} onApproveAgent={props.onApproveAgent} onRejectAgent={props.onRejectAgent} />;
  if (part.type === "artifacts") {
    return (
      <div className="agent-artifact-group">
        <div className="agent-artifact-group-head">
          <div>
            <span className="agent-artifact-group-title"><Layers size={12} /> 本轮产物</span>
            <span className="agent-artifact-group-subtitle">SQL、结果表、图表和洞察固定在当前回复中</span>
          </div>
          <span className="agent-artifact-count">{tab.artifacts?.length ?? 0}</span>
        </div>
        <div className="agent-artifact-renderer-wrap">
          <ArtifactRenderer artifacts={tab.artifacts ?? []} onOpenSqlConsole={props.onOpenSqlConsole} onSetSqlQuery={props.onSetSqlQuery} onToast={props.onToast} />
        </div>
      </div>
    );
  }
  if (part.type === "answer") return tab.agentAnswer ? <AnswerCard answer={tab.agentAnswer} /> : null;
  if (part.type === "suggestions") {
    return tab.agentSuggestions?.length ? <div className="agent-follow-up-in-thread"><FollowUpChips suggestions={tab.agentSuggestions} onSendFollowUp={props.onSendFollowUp} tabId={tab.id} /></div> : null;
  }
  if (part.type === "error") {
    return <div className="agent-inline-error"><AlertTriangle size={13} /><span>{part.text}</span></div>;
  }
  return null;
}

function buildMessageParts(tab: WorkspaceTab, message?: QueryMessage): MessagePart[] {
  const parts: MessagePart[] = [];
  const hasAnswer = Boolean(tab.agentAnswer?.answer || tab.agentAnswer?.key_findings?.length || tab.agentAnswer?.caveats?.length);
  const progressText = getProgressText(tab, message, hasAnswer);

  if (progressText) parts.push({ id: "progress", type: "text", text: progressText });
  if (tab.agentApproval) parts.push({ id: "approval", type: "approval", approval: tab.agentApproval });
  if (tab.artifacts?.length) parts.push({ id: "artifacts", type: "artifacts" });
  if (hasAnswer) parts.push({ id: "answer", type: "answer" });
  if (tab.agentStatus === "failed" && !hasAnswer) parts.push({ id: "error", type: "error", text: message?.text || "Agent 未能完成分析，可以重新生成或查看原始消息流。" });
  if (tab.agentStatus === "running" && parts.length === 0) parts.push({ id: "working", type: "text", text: "正在分析问题并等待第一个工具结果…" });
  if (tab.agentStatus === "completed" && tab.agentSuggestions?.length) parts.push({ id: "suggestions", type: "suggestions" });

  return parts;
}

function AgentNarration({ text, running }: { text: string; running: boolean }) {
  return (
    <div className="agent-narration-card">
      <div className="agent-narration-icon">{running ? <Clock3 size={12} /> : <CheckCircle2 size={12} />}</div>
      <div className="agent-narration-text">{text}</div>
    </div>
  );
}

function AgentApprovalCard({ tabId, approval, onApproveAgent, onRejectAgent }: { tabId: string; approval: AgentApprovalInfo; onApproveAgent: (tabId: string) => void; onRejectAgent: (tabId: string) => void }) {
  return (
    <div className={`agent-approval-inline ${approval.riskLevel === "danger" ? "agent-approval-danger" : ""}`}>
      <div className="agent-approval-inline-head">
        <ShieldAlert size={14} />
        <span>执行前需要确认</span>
        <strong>{RISK_LABELS[approval.riskLevel] || approval.riskLevel}</strong>
      </div>
      {approval.reason && <p>{approval.reason}</p>}
      {approval.sql && <pre>{approval.sql}</pre>}
      <div className="agent-approval-inline-actions">
        <button className="agent-approval-primary" onClick={() => onApproveAgent(tabId)}>批准并继续</button>
        <button className="agent-approval-secondary" onClick={() => onRejectAgent(tabId)}>拒绝</button>
      </div>
    </div>
  );
}

function getProgressText(tab: WorkspaceTab, message: QueryMessage | undefined, hasAnswer: boolean) {
  const text = message?.text?.trim() || "";
  if (hasAnswer && tab.agentStatus === "completed") return "";
  if (text === "思考中…") return "正在理解问题、选择工具并生成可验证的数据产物…";
  return text;
}
