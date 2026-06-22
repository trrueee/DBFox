import { useEffect, useRef } from "react";
import type { TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
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
  onOpenResultTab: (artifact: TableArtifact | ResultViewArtifact) => void;
}

export function MessageList({ messages, runs, artifacts, onOpenSqlConsole, onOpenResultTab }: MessageListProps) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, artifacts.length]);
  return (
    <div className="conv-message-scroll" ref={ref}>
      <div className="conv-message-column">
        {messages.map((message) => {
          const run = runs.find((item) => item.assistant_message_id === message.id);
          const messageArtifacts = artifacts.filter((artifact) => artifact.message_id === message.id);
          return (
            <MessageBubble
              key={message.id}
              message={message}
              run={run}
              artifacts={messageArtifacts}
              onOpenSqlConsole={onOpenSqlConsole}
              onOpenResultTab={onOpenResultTab}
            />
          );
        })}
      </div>
    </div>
  );
}
