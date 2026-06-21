import type {
  ConversationArtifact,
  ConversationMessage,
  ConversationRun,
} from "../../../types/conversation";
import { MarkdownContent } from "../../workspace/queryResult/MarkdownContent";
import { ArtifactEvidencePanel } from "./ArtifactEvidencePanel";
import { RunTracePanel } from "./RunTracePanel";

interface MessageBubbleProps {
  message: ConversationMessage;
  run?: ConversationRun;
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
}

export function MessageBubble({ message, run, artifacts, onOpenSqlConsole }: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <article className={`conv-message conv-message-${message.role}`}>
      <div className="conv-message-body">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <MarkdownContent content={message.content || (message.status === "streaming" ? "Thinking..." : "")} />
        )}
        {!isUser && run?.status === "failed" && (
          <div className="conv-error-card">{run.error_message || "Agent stopped."}</div>
        )}
        {!isUser && run && <RunTracePanel run={run} />}
        {!isUser && <ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={onOpenSqlConsole} />}
      </div>
    </article>
  );
}
