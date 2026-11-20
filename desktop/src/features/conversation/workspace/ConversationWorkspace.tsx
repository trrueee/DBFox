import { useCallback, useEffect, useId, useMemo, useState } from "react";
import type { ApprovalItem, ConversationEvidence, QuestionItem } from "../../../types/conversation";
import { AgentQuestion } from "../../../components/agent-elements/AgentQuestion";
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
import { useWorkbenchPresentation } from "../../resources/workbenchPresentation";
import { openComputerDock } from "../../computer/openComputerDock";

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
    cancelError,
    resolveApproval,
    resolvingApprovalId,
    approvalError,
    resolveQuestion,
    resolvingQuestionId,
    questionError,
    loadRunArtifacts,
  } = useConversationViewModel(conversationId);
  useWorkbenchPresentation(conversationId, cancelling || runningRun?.status === "cancelling" ? undefined : runningRun?.id, items);
  const references = useWorkspaceStore(selectActiveWorkbenchReferences);
  const [contentScrolled, setContentScrolled] = useState(false);
  const attentionId = useId();
  const removeWorkbenchReference = useWorkspaceStore((state) => state.removeWorkbenchReference);
  const clearWorkbenchReferences = useWorkspaceStore((state) => state.clearWorkbenchReferences);

  useEffect(() => {
    if (!detail && conversationId) void openConversation(conversationId);
  }, [conversationId, detail, openConversation]);

  const artifactRefsByRun = useMemo(() => {
    const refsByRun = new Map<string, Set<string>>();
    for (const item of items) {
      let referencedArtifactIds: string[] = [];
      if (item.type === "plan") referencedArtifactIds = item.payload.steps.flatMap(step => step.artifact_ids ?? []);
      else if (item.type === "function_call_output") referencedArtifactIds = item.payload.artifact_refs.map(reference => reference.artifact_id);
      else if (item.type === "message" && item.payload.role === "assistant") {
        referencedArtifactIds = [...item.payload.artifact_refs, ...item.payload.evidence].map(reference => reference.artifact_id);
      }
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
    const artifact = artifacts.find((candidate) => candidate.id === artifactId);
    openArtifactDock({ id: artifactId, title: artifact?.title ?? "关联成果" }, {
      projectId: detail?.project_id ?? undefined, sessionId: conversationId, preview: true,
    });
  }, [artifacts, conversationId, detail?.project_id]);

  const handleOpenEvidence = useCallback((evidence: ConversationEvidence) => {
    const artifact = artifacts.find(candidate => candidate.id === evidence.artifact_id);
    openArtifactDock({ id: evidence.artifact_id, title: artifact?.title ?? "引用来源" }, {
      projectId: detail?.project_id ?? undefined, sessionId: conversationId, evidenceId: evidence.id, preview: true,
    });
  }, [artifacts, conversationId, detail?.project_id]);

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
  const attention = runningRun?.status !== "cancelling" ? items.find(
    (item): item is ApprovalItem | QuestionItem => (item.type === "approval" || item.type === "question")
      && item.status === "waiting" && item.run_id === runningRun?.id,
  ) : undefined;

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
        onOpenEvidence={handleOpenEvidence}
        pinnedActionId={attention?.id}
        onFocusAction={() => document.getElementById(attentionId)?.focus({ preventScroll: false })}
        resolvingQuestionId={resolvingQuestionId}
        questionError={questionError}
        onResolveQuestion={resolveQuestion}
      />
      {attention && (
        <div id={attentionId} className="conv-pinned-action" tabIndex={-1} aria-label="等待你的操作">
          {attention.type === "approval" ? <ApprovalCard
            key={attention.id}
            approval={attention}
            pendingCount={pendingApprovals.length}
            onOpenSqlConsole={onOpenSqlConsole}
            submitting={resolvingApprovalId === attention.id}
            error={approvalError}
            onResolve={resolveApproval}
          /> : <AgentQuestion key={attention.id} question={attention}
            submitting={resolvingQuestionId === attention.id} error={questionError}
            onRespond={response => resolveQuestion(attention.run_id, attention.id, response)} />}
        </div>
      )}
      <Composer
        key={conversationId}
        conversationId={conversationId}
        context={<ComposerContext busy={sending} onOpenComputer={() => openComputerDock(conversationId)} />}
        running={Boolean(runningRun)}
        submitting={sending}
        cancelling={cancelling || runningRun?.status === "cancelling"}
        cancelError={cancelError}
        error={sendError}
        references={references}
        onRemoveReference={removeWorkbenchReference}
        onClearReferences={submitted => {
          const current = useWorkspaceStore.getState().workbenchByConversation[conversationId]?.references;
          if (current?.length === submitted.length && current.every((reference, index) => reference === submitted[index])) {
            clearWorkbenchReferences(conversationId);
          }
        }}
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
