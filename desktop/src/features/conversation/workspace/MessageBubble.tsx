import type { TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
import type {
  ConversationArtifact,
  ConversationMessage,
  ConversationRun,
} from "../../../types/conversation";
import { MarkdownContent } from "../../workspace/queryResult/MarkdownContent";
import { ArtifactEvidencePanel } from "./ArtifactEvidencePanel";
import { DataReferencePanel } from "./DataReferencePanel";
import { RunTracePanel } from "./RunTracePanel";

interface MessageBubbleProps {
  message: ConversationMessage;
  run?: ConversationRun;
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: TableArtifact | ResultViewArtifact) => void;
}

export function MessageBubble({ message, run, artifacts, onOpenSqlConsole, onOpenResultTab }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const messageClass = isUser ? `conv-message conv-message-${message.role}` : "conv-message conv-message-answer";
  return (
    <article className={messageClass}>
      <div className="conv-message-body">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <>
            {run && <RunTracePanel run={run} />}
            {run?.status === "failed" && (
              <div className="conv-error-card">{run.error_message || "Agent stopped."}</div>
            )}
            <div className="conv-answer-document">
              <MarkdownContent content={message.content || (message.status === "streaming" ? "Thinking..." : "")} />
            </div>
          </>
        )}
        {!isUser && <DataReferencePanel artifacts={artifacts} onOpenSqlConsole={onOpenSqlConsole} />}
        {!isUser && (
          <ArtifactEvidencePanel
            artifacts={artifacts}
            onOpenSqlConsole={onOpenSqlConsole}
            onOpenResultTab={onOpenResultTab}
          />
        )}
      </div>
    </article>
  );
}
