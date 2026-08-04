import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PanelRightOpen } from "lucide-react";
import {
  Group as PanelGroup,
  Panel,
  Separator as PanelResizeHandle,
  usePanelRef,
  type Layout,
} from "react-resizable-panels";
import type { ResultViewArtifact } from "../../../types/agentArtifact";
import type { ApprovalItem } from "../../../types/conversation";
import { Composer } from "./Composer";
import { ApprovalCard } from "./ApprovalCard";
import { ArtifactDock } from "./ArtifactDock";
import { ConversationHeader } from "./ConversationHeader";
import { MessageList } from "./MessageList";
import { useConversationViewModel } from "./useConversationViewModel";
import { isPrimaryConversationArtifact } from "./conversationArtifactModels";
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
    items,
    runs,
    artifacts,
    runningRun,
    openConversation,
    conversationLoadError,
    streamError,
    sendMessage,
    sending,
    sendError,
    cancelRun,
    cancelling,
    resolveApproval,
    resolvingApprovalId,
    approvalError,
    resolveQuestion,
    resolvingQuestionId,
    questionError,
    selectArtifact,
    loadRunArtifacts,
  } = useConversationViewModel(conversationId);
  const artifactPanelRef = usePanelRef();
  const pendingRevealArtifactIdRef = useRef<string | null>(null);
  const initialLayout = useMemo(() => readArtifactLayout(), []);
  const [artifactCollapsed, setArtifactCollapsed] = useState(
    () => Boolean(initialLayout && initialLayout.artifacts <= 0.01),
  );

  useEffect(() => {
    if (!detail && conversationId) void openConversation(conversationId);
  }, [conversationId, detail, openConversation]);

  const artifactRefsByRun = useMemo(() => {
    const refsByRun = new Map<string, Set<string>>();
    for (const item of items) {
      if (
        item.type !== "function_call_output"
        && !(item.type === "message" && item.payload.role === "assistant")
      ) continue;
      if (item.payload.artifact_refs.length === 0) continue;
      const artifactIds = refsByRun.get(item.run_id) ?? new Set<string>();
      for (const artifactRef of item.payload.artifact_refs) {
        artifactIds.add(artifactRef.artifact_id);
      }
      refsByRun.set(item.run_id, artifactIds);
    }
    return new Map(
      [...refsByRun].map(([runId, artifactIds]) => [runId, [...artifactIds]]),
    );
  }, [items]);
  const runIdByArtifactId = useMemo(() => {
    const runIds = new Map<string, string>();
    for (const [runId, artifactIds] of artifactRefsByRun) {
      for (const artifactId of artifactIds) runIds.set(artifactId, runId);
    }
    return runIds;
  }, [artifactRefsByRun]);

  useEffect(() => {
    for (const [runId, artifactIds] of artifactRefsByRun) {
      void loadRunArtifacts(conversationId, runId, artifactIds).catch(() => undefined);
    }
  }, [artifactRefsByRun, conversationId, loadRunArtifacts]);

  const primaryArtifacts = artifacts.filter(isPrimaryConversationArtifact);
  const hasArtifacts = primaryArtifacts.length > 0;
  useEffect(() => {
    const artifactId = pendingRevealArtifactIdRef.current;
    if (!artifactId || !primaryArtifacts.some((artifact) => artifact.id === artifactId)) return;
    pendingRevealArtifactIdRef.current = null;
    artifactPanelRef.current?.expand();
    setArtifactCollapsed(false);
  }, [artifactPanelRef, primaryArtifacts]);
  const handleSelectArtifact = useCallback((artifactId: string) => {
    if (primaryArtifacts.some((artifact) => artifact.id === artifactId)) {
      artifactPanelRef.current?.expand();
      setArtifactCollapsed(false);
    } else {
      const runId = runIdByArtifactId.get(artifactId);
      if (runId) {
        pendingRevealArtifactIdRef.current = artifactId;
        void loadRunArtifacts(conversationId, runId, [artifactId]).catch(() => {
          if (pendingRevealArtifactIdRef.current === artifactId) {
            pendingRevealArtifactIdRef.current = null;
          }
        });
      }
    }
    void selectArtifact(conversationId, artifactId);
  }, [
    artifactPanelRef,
    conversationId,
    loadRunArtifacts,
    primaryArtifacts,
    runIdByArtifactId,
    selectArtifact,
  ]);
  if (!detail) {
    return (
      <div className="conv-workspace" role={conversationLoadError ? "alert" : "status"}>
        <span>{conversationLoadError || "正在载入对话…"}</span>
        {conversationLoadError && (
          <button type="button" onClick={() => void openConversation(conversationId)}>
            重新载入
          </button>
        )}
      </div>
    );
  }
  const pendingApproval = items.findLast(
    (item): item is ApprovalItem => item.type === "approval" && item.status === "waiting",
  );

  const conversationPane = (
    <section className="conv-conversation-pane" aria-label="Conversation">
      <ConversationHeader detail={detail} onOpenHistory={onOpenHistory} onDelete={onDelete} />
      <MessageList
        items={items}
        runs={runs}
        artifacts={artifacts}
        onOpenSqlConsole={onOpenSqlConsole}
        onSelectArtifact={handleSelectArtifact}
        resolvingQuestionId={resolvingQuestionId}
        questionError={questionError}
        onResolveQuestion={resolveQuestion}
      />
      {pendingApproval && runningRun && (
        <div className="conv-pinned-action">
          <ApprovalCard
            approval={pendingApproval}
            onOpenSqlConsole={onOpenSqlConsole}
            submitting={resolvingApprovalId === pendingApproval.id}
            error={approvalError}
            onResolve={resolveApproval}
          />
        </div>
      )}
      <Composer
        running={Boolean(runningRun)}
        submitting={sending}
        cancelling={cancelling}
        error={sendError || streamError}
        onSend={(text, mode) => sendMessage(conversationId, text, mode)}
        onCancel={() => runningRun ? cancelRun(runningRun.id) : Promise.resolve()}
      />
    </section>
  );

  const artifactDock = hasArtifacts ? (
    <ArtifactDock
      artifacts={primaryArtifacts}
      selectedArtifactId={detail.selected_artifact_id}
      onSelectArtifact={handleSelectArtifact}
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
          resizeTargetMinimumSize={{ coarse: 24, fine: 12 }}
          onLayoutChanged={(layout) => {
            writeArtifactLayout(layout);
            setArtifactCollapsed(layout.artifacts <= 0.01);
          }}
        >
          <Panel id="conversation" className="conv-artifact-main-panel" defaultSize="72%" minSize="38%">
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
