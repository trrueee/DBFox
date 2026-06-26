import { useEffect, useState } from "react";
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from "react-resizable-panels";
import type { ResultViewArtifact } from "../../../types/agentArtifact";
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
  onOpenResultTab: (artifact: ResultViewArtifact) => void;
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

  const conversationPane = (
    <section className="conv-conversation-pane" aria-label="Conversation">
      <ConversationHeader detail={detail} onOpenHistory={onOpenHistory} onDelete={onDelete} />
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
  );

  const artifactDock = hasArtifacts ? (
    <ArtifactDock
      artifacts={artifacts}
      selectedArtifactId={selectedArtifactId}
      onSelectArtifact={selectArtifact}
      onOpenSqlConsole={onOpenSqlConsole}
      onOpenResultTab={onOpenResultTab}
    />
  ) : null;

  return (
    <div className={`conv-workspace ${hasArtifacts ? "has-artifact-dock" : ""}`}>
      {hasArtifacts ? (
        <PanelGroup orientation="horizontal" className="conv-artifact-panel-group">
          <Panel className="conv-artifact-main-panel" defaultSize="72%" minSize="48%">
            {conversationPane}
          </Panel>
          <PanelResizeHandle className="conv-artifact-resizer" aria-label="调整工件区宽度" />
          <Panel className="conv-artifact-dock-panel" defaultSize="28%" minSize="22%" maxSize="44%">
            {artifactDock}
          </Panel>
        </PanelGroup>
      ) : (
        conversationPane
      )}
    </div>
  );
}
