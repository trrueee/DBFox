import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApprovalItem } from "../../../types/conversation";
import { Composer } from "./Composer";
import { ApprovalCard } from "./ApprovalCard";
import { ConversationHeader } from "./ConversationHeader";
import { MessageList } from "./MessageList";
import { useConversationViewModel } from "./useConversationViewModel";
import "./conversationWorkspace.css";

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
  const [contentScrolled, setContentScrolled] = useState(false);

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

  useEffect(() => {
    for (const [runId, artifactIds] of artifactRefsByRun) {
      void loadRunArtifacts(conversationId, runId, artifactIds).catch(() => undefined);
    }
  }, [artifactRefsByRun, conversationId, loadRunArtifacts]);

  const handleSelectArtifact = useCallback((artifactId: string) => {
    void selectArtifact(conversationId, artifactId);
  }, [conversationId, selectArtifact]);

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
    <section
      className="conv-conversation-pane"
      aria-label="Conversation"
      data-content-scrolled={contentScrolled ? "true" : undefined}
    >
      <ConversationHeader detail={detail} />
      <MessageList
        items={items}
        runs={runs}
        artifacts={artifacts}
        onOpenSqlConsole={onOpenSqlConsole}
        onSelectArtifact={handleSelectArtifact}
        resolvingQuestionId={resolvingQuestionId}
        questionError={questionError}
        onResolveQuestion={resolveQuestion}
        onScrolledChange={setContentScrolled}
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
        onSend={async (text, mode, requestedResources) => {
          await sendMessage(conversationId, text, mode, requestedResources);
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
