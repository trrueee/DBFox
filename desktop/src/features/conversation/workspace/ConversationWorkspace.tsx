import { useEffect, useMemo } from "react";
import { useConversationStore } from "../../../stores/conversationStore";
import type { TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
import type {
  ConversationArtifact,
  ConversationMessage,
  ConversationRun,
} from "../../../types/conversation";
import { Composer } from "./Composer";
import { ConversationHeader } from "./ConversationHeader";
import { MessageList } from "./MessageList";
import "./conversationWorkspace.css";

export function ConversationWorkspace({
  conversationId,
  onOpenHistory,
  onOpenSqlConsole,
  onOpenResultTab,
  onDelete,
}: {
  conversationId: string;
  onOpenHistory: () => void;
  onOpenSqlConsole: (sql?: string) => void;
  onOpenResultTab: (artifact: TableArtifact | ResultViewArtifact) => void;
  onDelete: () => void;
}) {
  const store = useConversationStore();
  const detail = store.detailById[conversationId];
  useEffect(() => {
    if (!detail && conversationId) void store.openConversation(conversationId);
  }, [conversationId, detail, store]);
  const messages = useMemo<ConversationMessage[]>(
    () => detail?.messages.map((item) => store.messagesById[item.id] || item) || [],
    [detail, store.messagesById],
  );
  const runs = useMemo<ConversationRun[]>(
    () => detail?.runs.map((item) => store.runsById[item.id] || item) || [],
    [detail, store.runsById],
  );
  const artifacts = useMemo<ConversationArtifact[]>(
    () =>
      detail?.artifacts.map((item) => store.artifactsById[item.id] || item) ||
      Object.values(store.artifactsById).filter((item) => item.conversation_id === conversationId),
    [conversationId, detail, store.artifactsById],
  );
  const runningRun = runs.find((run) => run.status === "running" || run.status === "waiting_approval");
  if (!detail) return <div className="conv-workspace">Loading...</div>;
  return (
    <div className="conv-workspace">
      <ConversationHeader detail={detail} onOpenHistory={onOpenHistory} onDelete={onDelete} />
      <MessageList
        messages={messages}
        runs={runs}
        artifacts={artifacts}
        onOpenSqlConsole={onOpenSqlConsole}
        onOpenResultTab={onOpenResultTab}
      />
      <Composer
        running={Boolean(runningRun)}
        onSend={(text) => void store.sendMessage(conversationId, text)}
        onCancel={() => runningRun && store.cancelRun(runningRun.id)}
      />
    </div>
  );
}
