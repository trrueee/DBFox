import { useEffect, useMemo, useRef } from "react";
import type { ResultViewArtifact } from "../../../types/agentArtifact";
import type {
  ConversationArtifact,
  ConversationMessage,
  ConversationRun,
} from "../../../types/conversation";
import { MessageBubble } from "./MessageBubble";

interface MessageListProps {
  messages: ConversationMessage[];
  runs: ConversationRun[];
  artifacts: ConversationArtifact[];
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab: (artifact: ResultViewArtifact) => void;
  onResolveApproval: (runId: string, approvalId: string, approved: boolean) => void;
  onSelectArtifact?: (artifactId: string) => void;
}

export function MessageList({
  messages,
  runs,
  artifacts,
  onOpenSqlConsole,
  onOpenResultTab,
  onResolveApproval,
  onSelectArtifact,
}: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  const runsByAssistantMessageId = useMemo(
    () => new Map(runs.map((run) => [run.assistant_message_id, run])),
    [runs],
  );
  const artifactsByMessageId = useMemo(() => {
    const map = new Map<string, ConversationArtifact[]>();
    for (const artifact of artifacts) {
      const key = artifact.message_id || "";
      const existing = map.get(key);
      if (existing) {
        existing.push(artifact);
      } else {
        map.set(key, [artifact]);
      }
    }
    return map;
  }, [artifacts]);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, artifacts.length]);
  return (
    <div className="conv-message-scroll" ref={ref}>
      <div className="conv-message-column">
        {messages.map((message) => {
          const run = runsByAssistantMessageId.get(message.id);
          const messageArtifacts = artifactsByMessageId.get(message.id) || [];
          return (
            <MessageBubble
              key={message.id}
              message={message}
              run={run}
              artifacts={messageArtifacts}
              onOpenSqlConsole={onOpenSqlConsole}
              onOpenResultTab={onOpenResultTab}
              onResolveApproval={onResolveApproval}
              onSelectArtifact={onSelectArtifact}
            />
          );
        })}
      </div>
    </div>
  );
}
