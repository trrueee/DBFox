import { useEffect, useMemo, useState } from "react";
import { PanelRightOpen } from "lucide-react";
import {
  Group as PanelGroup,
  Panel,
  Separator as PanelResizeHandle,
  usePanelRef,
  type Layout,
} from "react-resizable-panels";
import type { ResultViewArtifact } from "../../../types/agentArtifact";
import { Composer } from "./Composer";
import { ApprovalCard } from "./ApprovalCard";
import { ArtifactDock } from "./ArtifactDock";
import { ConversationHeader } from "./ConversationHeader";
import { MessageList } from "./MessageList";
import { useConversationViewModel } from "./useConversationViewModel";
import "./conversationWorkspace.css";

const ARTIFACT_LAYOUT_KEY = "dbfox.conversation.artifact-layout.v1";

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
    resolveQuestion,
    selectArtifact,
  } = useConversationViewModel(conversationId);
  const artifactPanelRef = usePanelRef();
  const initialLayout = useMemo(() => readArtifactLayout(), []);
  const [artifactCollapsed, setArtifactCollapsed] = useState(
    () => Boolean(initialLayout && initialLayout.artifacts <= 0.01),
  );

  useEffect(() => {
    if (!detail && conversationId) void openConversation(conversationId);
  }, [conversationId, detail, openConversation]);

  if (!detail) return <div className="conv-workspace" role="status">正在载入对话…</div>;
  const hasArtifacts = artifacts.length > 0;
  const handleSelectArtifact = (artifactId: string) => void selectArtifact(conversationId, artifactId);
  const pendingApproval = runningRun?.approval?.status === "pending" ? runningRun.approval : null;

  const conversationPane = (
    <section className="conv-conversation-pane" aria-label="Conversation">
      <ConversationHeader detail={detail} onOpenHistory={onOpenHistory} onDelete={onDelete} />
      <MessageList
        messages={messages}
        runs={runs}
        artifacts={artifacts}
        activities={detail.activities}
        questions={detail.questions}
        onOpenSqlConsole={onOpenSqlConsole}
        onOpenResultTab={onOpenResultTab}
        onSelectArtifact={handleSelectArtifact}
        onResolveQuestion={(runId, questionId, response) => void resolveQuestion(runId, questionId, response)}
      />
      {pendingApproval && runningRun && (
        <div className="conv-pinned-action">
          <ApprovalCard
            runId={runningRun.id}
            approval={pendingApproval}
            onOpenSqlConsole={onOpenSqlConsole}
            onResolve={(runId, approvalId, approved) => void resolveApproval(runId, approvalId, approved)}
          />
        </div>
      )}
      <Composer
        running={Boolean(runningRun)}
        onSend={(text, mode) => void sendMessage(conversationId, text, mode)}
        onCancel={() => runningRun && cancelRun(runningRun.id)}
      />
    </section>
  );

  const artifactDock = hasArtifacts ? (
    <ArtifactDock
      artifacts={artifacts}
      selectedArtifactId={detail.selected_artifact_id}
      onSelectArtifact={handleSelectArtifact}
      onOpenSqlConsole={onOpenSqlConsole}
      onOpenResultTab={onOpenResultTab}
      onCollapse={() => artifactPanelRef.current?.collapse()}
    />
  ) : null;

  return (
    <div className={`conv-workspace ${hasArtifacts ? "has-artifact-dock" : ""}`}>
      {hasArtifacts ? (
        <PanelGroup
          id="conversation-artifact-layout"
          orientation="horizontal"
          className="conv-artifact-panel-group"
          defaultLayout={initialLayout}
          resizeTargetMinimumSize={{ coarse: 20, fine: 8 }}
          onLayoutChanged={(layout) => {
            writeArtifactLayout(layout);
            setArtifactCollapsed(layout.artifacts <= 0.01);
          }}
        >
          <Panel id="conversation" className="conv-artifact-main-panel" defaultSize="72%" minSize="48%">
            {conversationPane}
            {artifactCollapsed && (
              <button
                type="button"
                className="conv-artifact-restore"
                onClick={() => artifactPanelRef.current?.expand()}
                aria-label="展开工件区"
                title="展开工件区"
              >
                <PanelRightOpen size={16} aria-hidden="true" />
                <span>工件</span>
              </button>
            )}
          </Panel>
          <PanelResizeHandle className="conv-artifact-resizer" aria-label="调整工件区宽度" />
          <Panel
            id="artifacts"
            panelRef={artifactPanelRef}
            className="conv-artifact-dock-panel"
            defaultSize="28%"
            minSize="22%"
            maxSize="44%"
            collapsible
            collapsedSize={0}
          >
            {artifactDock}
          </Panel>
        </PanelGroup>
      ) : (
        conversationPane
      )}
    </div>
  );
}

function readArtifactLayout(): Layout | undefined {
  try {
    const raw = globalThis.localStorage?.getItem(ARTIFACT_LAYOUT_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.conversation !== "number" || typeof parsed.artifacts !== "number") return undefined;
    return { conversation: parsed.conversation, artifacts: parsed.artifacts };
  } catch {
    return undefined;
  }
}

function writeArtifactLayout(layout: Layout): void {
  try {
    globalThis.localStorage?.setItem(ARTIFACT_LAYOUT_KEY, JSON.stringify(layout));
  } catch {
    // Layout persistence is a convenience and must never block the workspace.
  }
}
