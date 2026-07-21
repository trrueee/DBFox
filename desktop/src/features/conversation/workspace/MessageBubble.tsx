import type { ResultViewArtifact } from "../../../types/agentArtifact";
import { AlertTriangle, CircleStop } from "lucide-react";
import type {
  ConversationArtifact,
  ConversationActivity,
  ConversationMessage,
  ConversationQuestion,
  ConversationRun,
} from "../../../types/conversation";
import { MarkdownContent } from "../../workspace/queryResult/MarkdownContent";
import { DataReferencePanel } from "./DataReferencePanel";
import { ActivityFeed } from "./ActivityFeed";
import { ApprovalAuditCard } from "./ApprovalCard";
import { QuestionCard } from "./QuestionCard";
import { useSmoothedStreamingText } from "./useSmoothedStreamingText";
import { getUserErrorMessage } from "../../../lib/api/client";
import { completionLimitationLabel } from "../../../lib/presentation";
import { buildAssistantMessageParts } from "./messageParts";

interface MessageBubbleProps {
  message: ConversationMessage;
  run?: ConversationRun;
  artifacts: ConversationArtifact[];
  activities?: ConversationActivity[];
  question?: ConversationQuestion;
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab?: (artifact: ResultViewArtifact) => void;
  onSelectArtifact?: (artifactId: string) => void;
  onResolveQuestion?: (
    runId: string,
    questionId: string,
    response: { selected_value?: string; text?: string },
  ) => void;
}

export function MessageBubble({
  message,
  run,
  artifacts,
  activities = [],
  question,
  onOpenSqlConsole,
  onSelectArtifact,
  onResolveQuestion,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const messageClass = isUser ? `conv-message conv-message-${message.role}` : "conv-message conv-message-answer";
  const smoothedAnswer = useSmoothedStreamingText(message.content, !isUser && message.status === "streaming", message.id);
  const answerContent = smoothedAnswer.text || (!run && message.status === "streaming" ? "正在分析问题…" : "");
  const parts = isUser ? [] : buildAssistantMessageParts({
    message,
    run,
    activities,
    artifacts,
    question,
    displayedAnswer: answerContent,
  });
  return (
    <article className={messageClass}>
      <div className="conv-message-body">
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          parts.map((part) => {
            if (part.type === "activity") {
              return <ActivityFeed key={part.id} activities={part.activities} onSelectArtifact={onSelectArtifact} />;
            }
            if (part.type === "error") {
              return <div key={part.id} className="conv-error-card" role="alert">
                {getUserErrorMessage(part.message, "本次分析未完成，请重试。")}
              </div>;
            }
            if (part.type === "cancelled") {
              return <div key={part.id} className="conv-run-cancelled" role="status">
                <CircleStop size={15} aria-hidden="true" />
                <span><strong>任务已停止</strong> 已产生的分析步骤和工件仍然保留。</span>
              </div>;
            }
            if (part.type === "approval" && run) {
              return part.approval.status === "pending" ? null : (
                <ApprovalAuditCard key={part.id} approval={part.approval} onOpenSqlConsole={onOpenSqlConsole} />
              );
            }
            if (part.type === "question" && run) {
              return <QuestionCard key={part.id} question={part.question}
                onRespond={(response) => onResolveQuestion?.(run.id, part.question.id, response)} />;
            }
            if (part.type === "answer") {
              return <div key={part.id} className="conv-answer-document"
                data-streaming-reveal={smoothedAnswer.isRevealing || undefined}>
                {run?.completion_disposition === "bounded_partial" && (
                  <div className="conv-completion-limitation" role="status">
                    <AlertTriangle size={15} aria-hidden="true" />
                    <div>
                      <strong>已完成当前可验证的分析</strong>
                      <span>{(run.limitation_codes || []).map(completionLimitationLabel).join("；")}</span>
                    </div>
                  </div>
                )}
                <MarkdownContent
                  content={part.content}
                  citations={run?.answer?.evidence}
                  onCitation={onSelectArtifact}
                />
              </div>;
            }
            if (part.type === "artifacts") {
              return <DataReferencePanel key={part.id} artifacts={part.artifacts}
                onOpenSqlConsole={onOpenSqlConsole} onSelectArtifact={onSelectArtifact} />;
            }
            return null;
          })
        )}
      </div>
    </article>
  );
}
