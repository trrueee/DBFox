import { useEffect, useState } from "react";
import type { TableArtifact, ResultViewArtifact } from "../../../types/agentArtifact";
import { Composer } from "./Composer";
import { ArtifactDock } from "./ArtifactDock";
import { ConversationHeader } from "./ConversationHeader";
import { MessageList } from "./MessageList";
import { useConversationViewModel } from "./useConversationViewModel";
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
  const [selectedArtifact, setSelectedArtifact] = useState<{ conversationId: string; artifactId: string } | null>(null);
  const {
    detail,
    messages,
    runs,
    artifacts,
    runningRun,
    openConversation,
    sendMessage,
    cancelRun,
    resolveApproval,
  } = useConversationViewModel(conversationId);

  useEffect(() => {
    if (!detail && conversationId) void openConversation(conversationId);
  }, [conversationId, detail, openConversation]);

  if (!detail) return <div className="conv-workspace">Loading...</div>;
  const hasArtifacts = artifacts.length > 0;
  const selectedArtifactId = selectedArtifact?.conversationId === conversationId ? selectedArtifact.artifactId : null;
  const selectArtifact = (artifactId: string) => setSelectedArtifact({ conversationId, artifactId });
  return (
    <div className="conv-workspace">
      <ConversationHeader detail={detail} onOpenHistory={onOpenHistory} onDelete={onDelete} />
      <div className={`conv-workspace-main ${hasArtifacts ? "has-artifact-dock" : ""}`}>
        <section className="conv-conversation-pane" aria-label="Conversation">
          <MessageList
            messages={messages}
            runs={runs}
            artifacts={artifacts}
            onOpenSqlConsole={onOpenSqlConsole}
            onOpenResultTab={onOpenResultTab}
            onResolveApproval={(runId, approvalId, approved) => void resolveApproval(runId, approvalId, approved)}
            onSelectArtifact={selectArtifact}
          />
          <Composer
            running={Boolean(runningRun)}
            onSend={(text) => void sendMessage(conversationId, text)}
            onCancel={() => runningRun && cancelRun(runningRun.id)}
          />
        </section>
        {hasArtifacts && (
          <ArtifactDock
            artifacts={artifacts}
            selectedArtifactId={selectedArtifactId}
            onSelectArtifact={selectArtifact}
            onOpenSqlConsole={onOpenSqlConsole}
            onOpenResultTab={onOpenResultTab}
          />
        )}
      </div>
    </div>
  );
}
