import { lazy, Suspense, useCallback, useState } from "react";
import { Plus } from "lucide-react";
import { useConversationStore } from "../../stores/conversationStore";
import {
  selectActiveWorkbenchReferences,
  useWorkspaceStore,
} from "../../stores/workspaceStore";
import { getUserErrorMessage } from "../../lib/api/client";
import { SmartQueryHome } from "../workspace/SmartQueryHome";
import { Button, EmptyState, ErrorState, LoadingState } from "../../components/ui";
import { ProjectOverview } from "../projects/ProjectOverview";
import type { WorkbenchReference } from "../../types/workspace";

const ConversationWorkspace = lazy(() =>
  import("../conversation/workspace/ConversationWorkspace").then((module) => ({ default: module.ConversationWorkspace })),
);
import "./ConversationCenter.css";

interface ConversationCenterProps {
  onNewProject: () => void;
}

interface PendingSubmission {
  conversationId: string;
  content: string;
  idempotencyKey: string;
  references: readonly WorkbenchReference[];
}

export function ConversationCenter({ onNewProject }: ConversationCenterProps) {
  const centerMode = useWorkspaceStore((s) => s.centerMode);
  const mainSurface = useWorkspaceStore((s) =>
    s.activeProjectId ? s.mainSurfaceByProject[s.activeProjectId] : undefined,
  );
  const pendingAsk = useWorkspaceStore((s) => s.pendingAsk);
  const clearPendingAsk = useWorkspaceStore((s) => s.clearPendingAsk);
  const openConversationCenter = useWorkspaceStore((s) => s.openConversationCenter);
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const references = useWorkspaceStore(selectActiveWorkbenchReferences);
  const setProjectActiveConversation = useWorkspaceStore(
    (state) => state.setProjectActiveConversation,
  );
  const promoteDraftWorkbenchToConversation = useWorkspaceStore(
    (state) => state.promoteDraftWorkbenchToConversation,
  );
  const removeWorkbenchReference = useWorkspaceStore((state) => state.removeWorkbenchReference);
  const clearWorkbenchReferences = useWorkspaceStore((state) => state.clearWorkbenchReferences);
  const [askInputValue, setAskInputValue] = useState("");
  const [submitError, setSubmitError] = useState<unknown | null>(null);
  const [pendingSubmission, setPendingSubmission] = useState<PendingSubmission | null>(null);
  const displayAsk = pendingAsk ?? askInputValue;

  const handleSubmitAsk = useCallback(async () => {
    const text = displayAsk.trim();
    if (!text) return;
    setSubmitError(null);
    try {
      let submission = pendingSubmission?.content === text ? pendingSubmission : null;
      if (!submission) {
        const detail = await useConversationStore.getState().createAndOpenConversation(text);
        submission = {
          conversationId: detail.id,
          content: text,
          idempotencyKey: globalThis.crypto.randomUUID(),
          references,
        };
        setPendingSubmission(submission);
      }
      await useConversationStore
        .getState()
        .sendMessage(
          submission.conversationId,
          submission.content,
          "queue",
          submission.idempotencyKey,
          submission.references,
        );
      promoteDraftWorkbenchToConversation(activeProjectId, submission.conversationId);
      setProjectActiveConversation(activeProjectId, submission.conversationId);
      openConversationCenter(submission.conversationId);
      clearPendingAsk();
      clearWorkbenchReferences();
      setAskInputValue("");
      setPendingSubmission(null);
    } catch (error) {
      setSubmitError(error);
    }
  }, [
    activeProjectId,
    clearPendingAsk,
    displayAsk,
    openConversationCenter,
    pendingSubmission,
    promoteDraftWorkbenchToConversation,
    references,
    setProjectActiveConversation,
    clearWorkbenchReferences,
  ]);

  if (!activeProjectId) {
    return (
      <section className="conversation-center" aria-label="对话">
        <EmptyState
          title="创建第一个项目"
          description="项目是 DBFox 的工作单元，创建后即可在中间用自然语言开始分析。"
          action={(
            <Button type="button" onClick={onNewProject}>
              <Plus size={14} aria-hidden="true" />
              新建项目
            </Button>
          )}
        />
      </section>
    );
  }

  const effectiveSurface = mainSurface ?? (
    centerMode === "conversation" ? { kind: "conversation" as const } : { kind: "new-conversation" as const }
  );

  if (effectiveSurface.kind === "conversation" && effectiveSurface.conversationId) {
    return (
      <section className="conversation-center" aria-label="对话">
        <Suspense fallback={<LoadingState label="正在载入对话" />}>
          <ConversationWorkspace conversationId={effectiveSurface.conversationId} />
        </Suspense>
      </section>
    );
  }

  if (effectiveSurface.kind === "project-overview") {
    return (
      <section className="conversation-center" aria-label="项目上下文">
        <ProjectOverview />
      </section>
    );
  }

  return (
    <section className="conversation-center" aria-label="对话">
      <SmartQueryHome
        askInputValue={displayAsk}
        onAskInputChange={(value) => {
          clearPendingAsk();
          setAskInputValue(value);
          setSubmitError(null);
          setPendingSubmission(null);
        }}
        onSubmitAsk={() => void handleSubmitAsk()}
        projectId={activeProjectId}
        references={references}
        onRemoveReference={(reference) => {
          removeWorkbenchReference(reference);
          setSubmitError(null);
          setPendingSubmission(null);
        }}
        feedback={submitError ? (
          <ErrorState
            title="无法开始任务"
            description={getUserErrorMessage(submitError, "创建任务失败，请重试。")}
            error={submitError}
            onRetry={() => void handleSubmitAsk()}
            retryLabel="重试发送"
          />
        ) : null}
      />
    </section>
  );
}
