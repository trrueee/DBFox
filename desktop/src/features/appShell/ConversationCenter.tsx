import { lazy, Suspense, useCallback, useState } from "react";
import { Plus } from "lucide-react";
import { useConversationStore } from "../../stores/conversationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { getUserErrorMessage } from "../../lib/api/client";
import { SmartQueryHome } from "../workspace/SmartQueryHome";
import { Button, EmptyState, LoadingState } from "../../components/ui";

const ConversationWorkspace = lazy(() =>
  import("../conversation/workspace/ConversationWorkspace").then((module) => ({ default: module.ConversationWorkspace })),
);
import "./ConversationCenter.css";

interface ConversationCenterProps {
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
  onNewProject: () => void;
}

export function ConversationCenter({ showToast, onNewProject }: ConversationCenterProps) {
  const centerMode = useWorkspaceStore((s) => s.centerMode);
  const mainSurface = useWorkspaceStore((s) =>
    s.activeProjectId ? s.mainSurfaceByProject[s.activeProjectId] : undefined,
  );
  const pendingAsk = useWorkspaceStore((s) => s.pendingAsk);
  const clearPendingAsk = useWorkspaceStore((s) => s.clearPendingAsk);
  const openConversationCenter = useWorkspaceStore((s) => s.openConversationCenter);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const [askInputValue, setAskInputValue] = useState("");
  const displayAsk = pendingAsk ?? askInputValue;

  const handleSubmitAsk = useCallback(async () => {
    const text = displayAsk.trim();
    if (!text) return;
    try {
      const detail = await useConversationStore.getState().createAndOpenConversation(
        text,
        [],
      );
      await useConversationStore
        .getState()
        .sendMessage(detail.id, text, "queue", globalThis.crypto.randomUUID());
      clearPendingAsk();
      openConversationCenter(detail.id);
      setAskInputValue("");
    } catch (error) {
      showToast(getUserErrorMessage(error, "创建智能分析失败，请重试。"), "error");
    }
  }, [clearPendingAsk, displayAsk, openConversationCenter, showToast]);

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

  if (effectiveSurface.kind === "conversation" && activeConversationId) {
    return (
      <section className="conversation-center" aria-label="对话">
        <Suspense fallback={<LoadingState label="正在载入对话" />}>
          <ConversationWorkspace conversationId={activeConversationId} />
        </Suspense>
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
        }}
        onSubmitAsk={() => void handleSubmitAsk()}
        projectId={activeProjectId}
      />
    </section>
  );
}
