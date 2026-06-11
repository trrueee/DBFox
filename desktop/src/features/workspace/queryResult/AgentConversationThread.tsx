import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3, Layers, Loader2, ShieldAlert, Sparkles, User } from "lucide-react";
import { useMemo, useState } from "react";
import type { AgentApprovalInfo, WorkspaceTab } from "../../../mock/databoxMock";
import type { AgentAnswer, AgentMessageBlock, AgentRuntimeEvent, FollowUpSuggestion } from "../../../lib/api/types";
import type { AgentArtifact as ViewAgentArtifact } from "../../../types/agentArtifact";
import { ArtifactRenderer } from "../artifacts/ArtifactRenderer";
import { AnswerCard } from "./AnswerCard";
import { FollowUpChips } from "./FollowUpChips";
import { QueryMessages } from "./QueryMessages";
import "./AgentConversationThread.css";

type QueryMessage = NonNullable<WorkspaceTab["chatMessages"]>[number];

type MessagePart =
  | { id: string; type: "text"; text: string }
  | { id: string; type: "timeline"; events: AgentRuntimeEvent[] }
  | { id: string; type: "approval"; approval: AgentApprovalInfo }
  | { id: string; type: "artifact_ref"; artifactId: string; display?: "compact" | "full" | null }
  | { id: string; type: "artifacts" }
  | { id: string; type: "answer"; answer: AgentAnswer }
  | { id: string; type: "suggestions"; suggestions: FollowUpSuggestion[] }
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
  if (part.type === "timeline") return <AgentTimelineCard events={part.events} status={tab.agentStatus} />;
  if (part.type === "approval") return <AgentApprovalCard tabId={tab.id} approval={part.approval} onApproveAgent={props.onApproveAgent} onRejectAgent={props.onRejectAgent} />;
  if (part.type === "artifact_ref") {
    const artifacts = findReferencedArtifacts(tab.artifacts || [], part.artifactId);
    return <AgentArtifactBlock artifacts={artifacts} count={artifacts.length} compact={part.display === "compact"} {...props} />;
  }
  if (part.type === "artifacts") {
    return <AgentArtifactBlock artifacts={tab.artifacts ?? []} count={tab.artifacts?.length ?? 0} {...props} />;
  }
  if (part.type === "answer") return <AnswerCard answer={part.answer} />;
  if (part.type === "suggestions") {
    return part.suggestions.length ? <div className="agent-follow-up-in-thread"><FollowUpChips suggestions={part.suggestions} onSendFollowUp={props.onSendFollowUp} tabId={tab.id} /></div> : null;
  }
  if (part.type === "error") {
    return <div className="agent-inline-error"><AlertTriangle size={13} /><span>{part.text}</span></div>;
  }
  return null;
}

function AgentArtifactBlock(props: AgentConversationThreadProps & { artifacts: ViewAgentArtifact[]; count: number; compact?: boolean }) {
  const { artifacts, count, compact } = props;
  if (count === 0) return null;

  return (
    <div className={`agent-artifact-group ${compact ? "agent-artifact-group-compact" : ""}`}>
      <div className="agent-artifact-group-head">
        <div>
          <span className="agent-artifact-group-title"><Layers size={12} /> 本轮产物</span>
          <span className="agent-artifact-group-subtitle">SQL、结果表、图表和洞察固定在当前回复中</span>
        </div>
        <span className="agent-artifact-count">{count}</span>
      </div>
      <div className="agent-artifact-renderer-wrap">
        <ArtifactRenderer artifacts={artifacts} onOpenSqlConsole={props.onOpenSqlConsole} onSetSqlQuery={props.onSetSqlQuery} onToast={props.onToast} />
      </div>
    </div>
  );
}

function buildMessageParts(tab: WorkspaceTab, message?: QueryMessage): MessagePart[] {
  const parts: MessagePart[] = [];
  const backendParts = buildPartsFromBlocks(tab.agentMessageBlocks || [], tab);
  const hasAnswer = Boolean(tab.agentAnswer?.answer || tab.agentAnswer?.key_findings?.length || tab.agentAnswer?.caveats?.length);
  const progressText = getProgressText(tab, message, hasAnswer || backendParts.some((part) => part.type === "answer"));
  const events = tab.agentRuntimeEvents || [];

  if (backendParts.length > 0) {
    if (progressText && tab.agentStatus === "running" && !backendParts.some((part) => part.type === "text")) parts.push({ id: "progress", type: "text", text: progressText });
    if (events.length) parts.push({ id: "timeline", type: "timeline", events });
    if (tab.agentApproval) parts.push({ id: "approval", type: "approval", approval: tab.agentApproval });
    parts.push(...backendParts);
    if (tab.agentStatus === "failed" && !backendParts.some((part) => part.type === "answer")) parts.push({ id: "error", type: "error", text: message?.text || "Agent 未能完成分析，可以重新生成或查看原始消息流。" });
    return parts;
  }

  if (progressText) parts.push({ id: "progress", type: "text", text: progressText });
  if (events.length) parts.push({ id: "timeline", type: "timeline", events });
  if (tab.agentApproval) parts.push({ id: "approval", type: "approval", approval: tab.agentApproval });
  if (tab.artifacts?.length) parts.push({ id: "artifacts", type: "artifacts" });
  if (tab.agentAnswer && hasAnswer) parts.push({ id: "answer", type: "answer", answer: tab.agentAnswer });
  if (tab.agentStatus === "failed" && !hasAnswer) parts.push({ id: "error", type: "error", text: message?.text || "Agent 未能完成分析，可以重新生成或查看原始消息流。" });
  if (tab.agentStatus === "running" && parts.length === 0) parts.push({ id: "working", type: "text", text: "正在分析问题并等待第一个工具结果…" });
  if (tab.agentStatus === "completed" && tab.agentSuggestions?.length) parts.push({ id: "suggestions", type: "suggestions", suggestions: tab.agentSuggestions });

  return parts;
}

function buildPartsFromBlocks(blocks: AgentMessageBlock[], tab: WorkspaceTab): MessagePart[] {
  return [...blocks]
    .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0))
    .flatMap((block, index): MessagePart[] => {
      const id = block.block_id || `block-${index}-${block.type}`;
      if (block.type === "text" && block.content?.trim()) return [{ id, type: "text", text: block.content.trim() }];
      if (block.type === "artifact_ref" && block.artifact_id) return [{ id, type: "artifact_ref", artifactId: block.artifact_id, display: block.display }];
      if (block.type === "answer" && (block.answer || tab.agentAnswer)) return [{ id, type: "answer", answer: (block.answer || tab.agentAnswer)! }];
      if (block.type === "suggestions") {
        const suggestions = block.suggestions?.length ? block.suggestions : tab.agentSuggestions || [];
        return suggestions.length ? [{ id, type: "suggestions", suggestions }] : [];
      }
      return [];
    });
}

function AgentNarration({ text, running }: { text: string; running: boolean }) {
  return (
    <div className="agent-narration-card">
      <div className="agent-narration-icon">{running ? <Clock3 size={12} /> : <CheckCircle2 size={12} />}</div>
      <div className="agent-narration-text">{text}</div>
    </div>
  );
}

function AgentTimelineCard({ events, status }: { events: AgentRuntimeEvent[]; status?: WorkspaceTab["agentStatus"] }) {
  const [expanded, setExpanded] = useState(status === "running");
  const visibleEvents = expanded ? events : events.slice(-4);
  const hiddenCount = Math.max(0, events.length - visibleEvents.length);

  return (
    <div className="agent-timeline-card">
      <button className="agent-timeline-head" onClick={() => setExpanded((value) => !value)}>
        <span>{expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />} 执行流</span>
        <strong>{events.length}</strong>
      </button>
      <div className="agent-timeline-list">
        {!expanded && hiddenCount > 0 && <div className="agent-timeline-muted">已折叠 {hiddenCount} 条早期事件</div>}
        {visibleEvents.map((event) => (
          <div key={event.event_id || `${event.sequence}-${event.type}`} className={`agent-timeline-item ${event.type.includes("failed") ? "agent-timeline-item-error" : ""}`}>
            <span className="agent-timeline-dot">{event.type.includes("completed") ? <CheckCircle2 size={10} /> : event.type.includes("failed") ? <AlertTriangle size={10} /> : <Clock3 size={10} />}</span>
            <span className="agent-timeline-label">{formatRuntimeEvent(event)}</span>
          </div>
        ))}
      </div>
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

function findReferencedArtifacts(artifacts: ViewAgentArtifact[], artifactId: string) {
  return artifacts.filter((artifact) => artifact.id === artifactId);
}

function formatRuntimeEvent(event: AgentRuntimeEvent) {
  const stepName = firstString(event.step, ["title", "name", "node_name"]);
  if (event.type === "agent.step.started") return stepName ? `开始：${stepName}` : "开始执行步骤";
  if (event.type === "agent.step.completed") return stepName ? `完成：${stepName}` : "步骤完成";
  if (event.type === "agent.artifact.created") return event.artifact?.title ? `生成产物：${event.artifact.title}` : "生成新产物";
  if (event.type === "agent.approval.required") return "等待用户审批";
  if (event.type === "agent.answer.completed") return "回答生成完成";
  if (event.type === "agent.run.completed") return "运行完成";
  if (event.type === "agent.run.failed") return event.error ? `运行失败：${event.error}` : "运行失败";
  return stepName ? `${event.type} · ${stepName}` : event.type;
}

function firstString(source: Record<string, unknown> | null | undefined, keys: string[]) {
  if (!source) return "";
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function getProgressText(tab: WorkspaceTab, message: QueryMessage | undefined, hasAnswer: boolean) {
  const text = message?.text?.trim() || "";
  if (hasAnswer && tab.agentStatus === "completed") return "";
  if (text === "思考中…") return "正在理解问题、选择工具并生成可验证的数据产物…";
  return text;
}
