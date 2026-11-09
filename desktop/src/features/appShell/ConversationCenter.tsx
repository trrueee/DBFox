import { lazy, Suspense, useCallback, useState } from "react";
import {
  PlusIcon,
} from "@/components/icons";
import { useConversationStore } from "../../stores/conversationStore";
import {
  selectActiveWorkbenchReferences,
  useWorkspaceStore,
  selectActiveWorkbench,
  selectActiveWorkbenchScopeId,
} from "../../stores/workspaceStore";
import { getUserErrorMessage } from "../../lib/api/client";
import { SmartQueryHome } from "../workspace/SmartQueryHome";
import { Button, EmptyState, ErrorState, LoadingState } from "../../components/ui";
import { ProjectOverview } from "../projects/ProjectOverview";
import type { WorkbenchReference } from "../../types/workspace";
import { useAttachmentInput } from "../conversation/useAttachmentInput";
import { openWorkbenchReference } from "../resources/openWorkbenchReference";
import { captureWorkbenchInput } from "../resources/workbenchInput";
import { ComposerContext } from "../conversation/workspace/ComposerContext";

const ConversationWorkspace = lazy(() =>
  import("../conversation/workspace/ConversationWorkspace").then((module) => ({ default: module.ConversationWorkspace })),
);
import "./ConversationCenter.css";

interface ConversationCenterProps {
  onNewProject: () => void;
}

interface PendingSubmission {
  scopeId: string;
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
  const askInputValue = useWorkspaceStore(state => selectActiveWorkbench(state).draftInput ?? "");
  const setAskInputValue = useWorkspaceStore(state => state.setDraftInput);
  const [submitting, setSubmitting] = useState(false);
  const activeScope = useWorkspaceStore(selectActiveWorkbenchScopeId);
  const [submitFailure, setSubmitFailure] = useState<{ projectId: string; scopeId: string; error: unknown } | null>(null);
  const submitError = submitFailure?.projectId === activeProjectId && submitFailure.scopeId === activeScope ? submitFailure.error : null;
  const [pendingSubmission, setPendingSubmission] = useState<PendingSubmission | null>(null);
  const displayAsk = pendingAsk ?? askInputValue;
  const ensureDraftConversation = async () => {
    const state = useWorkspaceStore.getState();
    const existing = selectActiveWorkbench(state).draftConversationId;
    if (existing) return existing;
    const capturedScope = state.ensureActiveWorkbenchScope();
    const detail = await useConversationStore.getState().createAndOpenConversation(displayAsk.trim() || "附件分析");
    if (selectActiveWorkbenchScopeId(useWorkspaceStore.getState()) !== capturedScope) throw new Error("会话已切换。");
    useWorkspaceStore.getState().setDraftConversationId(detail.id);
    return detail.id;
  };
  const attachment = useAttachmentInput(ensureDraftConversation, references);

  const handleSubmitAsk = useCallback(async () => {
    const text = displayAsk.trim();
    if (!text || attachment.busy || submitting) return;
    const capturedScope = useWorkspaceStore.getState().ensureActiveWorkbenchScope();
    setSubmitting(true);
    setSubmitFailure(null);
    try {
      let submission = pendingSubmission?.scopeId === capturedScope && pendingSubmission.content === text ? pendingSubmission : null;
      if (!submission) {
        const draftId = selectActiveWorkbench(useWorkspaceStore.getState()).draftConversationId;
        const capturedReferences = captureWorkbenchInput(references, draftId ?? null);
        const conversationId = draftId ?? (await useConversationStore.getState().createAndOpenConversation(text)).id;
        submission = {
          scopeId: capturedScope,
          conversationId,
          content: text,
          idempotencyKey: globalThis.crypto.randomUUID(),
          references: capturedReferences,
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
      if (useWorkspaceStore.getState().activeProjectId !== activeProjectId
        || selectActiveWorkbenchScopeId(useWorkspaceStore.getState()) !== capturedScope) return;
      promoteDraftWorkbenchToConversation(activeProjectId, submission.conversationId);
      setProjectActiveConversation(activeProjectId, submission.conversationId);
      openConversationCenter(submission.conversationId);
      clearPendingAsk();
      clearWorkbenchReferences();
      setAskInputValue("");
      setPendingSubmission(null);
    } catch (error) {
      if (useWorkspaceStore.getState().activeProjectId === activeProjectId
        && selectActiveWorkbenchScopeId(useWorkspaceStore.getState()) === capturedScope) setSubmitFailure({ projectId: activeProjectId, scopeId: capturedScope, error });
    } finally { setSubmitting(false); }
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
    setAskInputValue,
    attachment.busy,
    submitting,
  ]);

  if (!activeProjectId) {
    return (
      <section className="conversation-center" aria-label="对话">
        <EmptyState
          title="打开文件夹，开始工作"
          description="在文件夹中对话、查看文件和处理数据。"
          action={(
            <Button type="button" onClick={onNewProject}>
              <PlusIcon size={16} aria-hidden="true" />
              打开文件夹
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
        <ProjectOverview key={activeProjectId} />
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
          setSubmitFailure(null);
          setPendingSubmission(null);
        }}
        onSubmitAsk={() => void handleSubmitAsk()}
        projectId={activeProjectId}
        context={<ComposerContext busy={submitting || attachment.busy} />}
        references={references}
        onAddAttachment={() => { setPendingSubmission(null); void attachment.add(); }}
        onOpenReference={(ref) => {
          const id = selectActiveWorkbench(useWorkspaceStore.getState()).draftConversationId;
          try { openWorkbenchReference(ref, id ?? undefined); } catch (error) { setSubmitFailure({ projectId: activeProjectId, scopeId: activeScope, error }); }
        }}
        attachmentBusy={attachment.busy}
        submitting={submitting}
        attachmentError={attachment.error}
        onRetryAttachment={attachment.retryable ? () => void attachment.retry() : undefined}
        onRemoveReference={(reference) => {
          removeWorkbenchReference(reference);
          attachment.remove(reference, selectActiveWorkbench(useWorkspaceStore.getState()).draftConversationId);
          setSubmitFailure(null);
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
