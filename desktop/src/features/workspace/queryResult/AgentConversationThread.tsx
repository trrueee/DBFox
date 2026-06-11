import { Loader2, Sparkles, User, Layers } from "lucide-react";
import type { WorkspaceTab } from "../../../mock/databoxMock";
import { AnswerCard } from "./AnswerCard";
import { FollowUpChips } from "./FollowUpChips";
import "./AgentConversationThread.css";

type QueryMessage = NonNullable<WorkspaceTab["chatMessages"]>[number];

interface AgentConversationThreadProps {
  tab: WorkspaceTab;
  onSendFollowUp: (tabId: string, text: string) => void;
}

export function AgentConversationThread({ tab, onSendFollowUp }: AgentConversationThreadProps) {
  const messages = tab.chatMessages?.length
    ? tab.chatMessages
    : tab.queryText?.trim()
      ? [{ id: -1, sender: "user" as const, text: tab.queryText.trim() }]
      : [];
  const lastAssistantId = [...messages].reverse().find((message) => message.sender === "ai")?.id;

  return (
    <div className="agent-thread">
      {messages.map((message) => {
        if (message.sender === "user") return <UserTurn key={message.id} message={message} />;
        if (message.id !== lastAssistantId) return <AssistantTextTurn key={message.id} message={message} />;
        return <AssistantRunTurn key={message.id} tab={tab} message={message} onSendFollowUp={onSendFollowUp} />;
      })}
      {messages.every((message) => message.sender !== "ai") && <AssistantRunTurn tab={tab} onSendFollowUp={onSendFollowUp} />}
    </div>
  );
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

function AssistantRunTurn({ tab, message, onSendFollowUp }: { tab: WorkspaceTab; message?: QueryMessage; onSendFollowUp: (tabId: string, text: string) => void }) {
  const isRunning = tab.agentStatus === "running";
  const hasAnswer = Boolean(tab.agentAnswer?.answer || tab.agentAnswer?.key_findings?.length || tab.agentAnswer?.caveats?.length);
  const text = message?.text?.trim() || "";
  const progressText = hasAnswer && tab.agentStatus === "completed" ? "" : text === "思考中…" ? "正在理解问题并生成可验证的数据产物…" : text;

  return (
    <div className="agent-turn agent-turn-assistant">
      <div className="agent-avatar agent-avatar-ai">
        {isRunning ? <Loader2 size={13} className="agent-spin" /> : <Sparkles size={13} />}
      </div>
      <div className="agent-assistant-bubble">
        <div className="agent-run-head">
          <div className="agent-run-title"><Sparkles size={13} /><span>DataBox Agent</span></div>
          <span className={`agent-status-pill agent-status-${tab.agentStatus || "running"}`}>{tab.agentStatus || "running"}</span>
        </div>

        {progressText && <div className="agent-narration-card">{progressText}</div>}

        {Boolean(tab.artifacts?.length) && (
          <div className="agent-artifact-group">
            <div className="agent-artifact-group-head">
              <span className="agent-artifact-group-title"><Layers size={12} /> 本轮产物</span>
              <span className="agent-artifact-count">{tab.artifacts?.length ?? 0}</span>
            </div>
            <div className="agent-artifact-list">
              {(tab.artifacts ?? []).map((artifact) => (
                <div key={artifact.id} className={`agent-artifact-mini agent-artifact-mini-${artifact.type}`}>
                  <strong>{artifact.title}</strong>
                  {artifact.description && <span>{artifact.description}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {hasAnswer && tab.agentAnswer && <AnswerCard answer={tab.agentAnswer} />}

        {tab.agentStatus === "completed" && tab.agentSuggestions && tab.agentSuggestions.length > 0 && (
          <div className="agent-follow-up-in-thread">
            <FollowUpChips suggestions={tab.agentSuggestions} onSendFollowUp={onSendFollowUp} tabId={tab.id} />
          </div>
        )}
      </div>
    </div>
  );
}
