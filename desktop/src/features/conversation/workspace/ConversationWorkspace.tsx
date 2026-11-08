import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApprovalItem } from "../../../types/conversation";
import { Button, ErrorState, ShadcnSkeleton as Skeleton } from "../../../components/ui";
import { getUserErrorMessage } from "../../../lib/api/client";
import { Composer } from "./Composer";
import { ComposerContext } from "./ComposerContext";
import { ApprovalCard } from "./ApprovalCard";
import { ConversationStreamNotice } from "./ConversationStreamNotice";
import { MessageList } from "./MessageList";
import { useConversationViewModel } from "./useConversationViewModel";
import {
  selectActiveWorkbenchReferences,
  useWorkspaceStore,
} from "../../../stores/workspaceStore";
import "./conversationWorkspace.css";
import { openArtifactDock } from "../../../stores/artifactDockStore";

export function ConversationWorkspace({
  conversationId,
  onOpenSqlConsole,
}: {
  conversationId: string;
  onOpenSqlConsole?: (sql?: string) => void;
}) {
  const {
    detail,
    items,
    runs,
    artifacts,
    runningRun,
    openConversation,
    conversationLoadError,
    hasOlderHistory,
    loadOlderHistory,
    loadingOlderHistory,
    olderHistoryLoaded,
    historyLoadError,
    streamError,
    streamState,
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
  const references = useWorkspaceStore(selectActiveWorkbenchReferences);
  const [contentScrolled, setContentScrolled] = useState(false);
  const removeWorkbenchReference = useWorkspaceStore((state) => state.removeWorkbenchReference);
  const clearWorkbenchReferences = useWorkspaceStore((state) => state.clearWorkbenchReferences);

  useEffect(() => {
    if (!detail && conversationId) void openConversation(conversationId);
  }, [conversationId, detail, openConversation]);

  const artifactRefsByRun = useMemo(() => {
    const refsByRun = new Map<string, Set<string>>();
    for (const item of items) {
      const referencedArtifactIds = item.type === "plan"
        ? item.payload.steps.flatMap((step) => step.artifact_ids ?? [])
        : item.type === "function_call_output"
          || (item.type === "message" && item.payload.role === "assistant")
          ? item.payload.artifact_refs.map((reference) => reference.artifact_id)
          : [];
      if (referencedArtifactIds.length === 0) continue;
      const artifactIds = refsByRun.get(item.run_id) ?? new Set<string>();
      for (const artifactId of referencedArtifactIds) {
        artifactIds.add(artifactId);
      }
      refsByRun.set(item.run_id, artifactIds);
    }
    return new Map(
      [...refsByRun].map(([runId, artifactIds]) => [runId, [...artifactIds]]),
    );
  }, [items]);

  useEffect(() => {
    for (const [runId, artifactIds] of artifactRefsByRun) {
      void loadRunArtifacts(conversationId, runId, artifactIds).catch(() => undefined);
    }
  }, [artifactRefsByRun, conversationId, loadRunArtifacts]);

  const handleSelectArtifact = useCallback((artifactId: string) => {
    void selectArtifact(conversationId, artifactId);
    const artifact = artifacts.find((candidate) => candidate.id === artifactId);
    if (artifact) openArtifactDock(artifact);
  }, [artifacts, conversationId, selectArtifact]);

  if (!detail) {
    return (
      <div className="conv-workspace">
        <section className="conv-conversation-pane" aria-label="对话内容">
        <div className="conv-loading-body" role={conversationLoadError ? undefined : "status"} aria-label={conversationLoadError ? undefined : "正在载入对话"}>
        {conversationLoadError ? (
          <div>
          <ErrorState
            title="对话载入失败"
            description={getUserErrorMessage(conversationLoadError, "对话载入失败，请重试。")}
            error={conversationLoadError}
            onRetry={() => void openConversation(conversationId)}
            retryLabel="重新载入"
          />
          <Button type="button" variant="ghost" onClick={() => useWorkspaceStore.getState().showSmartQueryHome()}>返回新任务</Button>
          </div>
        ) : (
          <div className="conv-loading-document"><Skeleton /><Skeleton /><Skeleton /><Skeleton /><span className="sr-only">正在载入对话</span></div>
        )}
        </div>
        <Composer key={conversationId} conversationId={conversationId} running={false}
          disabled={conversationLoadError ? "对话暂不可用" : "正在载入对话…"}
          onSend={async () => {}} onCancel={async () => {}} context={<ComposerContext busy />} />
        </section>
      </div>
    );
  }
  const pendingApprovals = items.filter(
    (item): item is ApprovalItem => item.type === "approval" && item.status === "waiting" && item.run_id === runningRun?.id,
  );
  const pendingApproval = pendingApprovals[0];

  const conversationPane = (
    <section
      className="conv-conversation-pane"
      aria-label="Conversation"
      data-content-scrolled={contentScrolled || undefined}
    >
      <ConversationStreamNotice
        state={streamState}
        error={streamError}
        onRefresh={() => openConversation(conversationId)}
      />
      <MessageList
        items={items}
        runs={runs}
        artifacts={artifacts}
        hasOlderHistory={hasOlderHistory}
        loadingOlderHistory={loadingOlderHistory}
        olderHistoryLoaded={olderHistoryLoaded}
        historyLoadError={historyLoadError}
        onLoadOlderHistory={loadOlderHistory}
        onOpenSqlConsole={onOpenSqlConsole}
        onScrolledChange={setContentScrolled}
        onSelectArtifact={handleSelectArtifact}
        resolvingQuestionId={resolvingQuestionId}
        questionError={questionError}
        onResolveQuestion={resolveQuestion}
      />
      {pendingApproval && runningRun && (
        <div className="conv-pinned-action">
          <ApprovalCard
            approval={pendingApproval}
            pendingCount={pendingApprovals.length}
            onOpenSqlConsole={onOpenSqlConsole}
            submitting={resolvingApprovalId === pendingApproval.id}
            error={approvalError}
            onResolve={resolveApproval}
          />
        </div>
      )}
      <Composer
        key={conversationId}
        conversationId={conversationId}
        context={<ComposerContext busy={sending} />}
        running={Boolean(runningRun)}
        submitting={sending}
        cancelling={cancelling}
        error={sendError}
        references={references}
        onRemoveReference={removeWorkbenchReference}
        onClearReferences={() => clearWorkbenchReferences(conversationId)}
        onSend={async (text, mode, references) => {
          await sendMessage(
            conversationId,
            text,
            mode,
            references,
          );
        }}
        onCancel={() => runningRun ? cancelRun(runningRun.id) : Promise.resolve()}
      />
    </section>
  );

  return (
    <div className="conv-workspace">
      {conversationPane}
    </div>
  );
}
