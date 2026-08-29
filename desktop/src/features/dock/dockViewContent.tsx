import { lazy, Suspense, useEffect, useMemo, useRef } from "react";
import { MessageSquarePlus } from "lucide-react";
import { Button, EmptyState, LoadingState } from "../../components/ui";
import { openArtifactDock } from "../../stores/artifactDockStore";
import { useConversationStore } from "../../stores/conversationStore";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useConversationViewModel } from "../conversation/workspace/useConversationViewModel";
import { isPrimaryConversationArtifact } from "../conversation/workspace/conversationArtifactSelectors";
import { ArtifactViewHost } from "../workspace/artifacts/ArtifactViewHost";
import { WorkspaceShell } from "../workspace/WorkspaceShell";
import type { WorkspaceDockTab } from "../../types/workspace";
import type { DockShowToast } from "./types";
import { toArtifactEnvelope } from "../workspace/artifacts/artifactEnvelope";

const ArtifactDock = lazy(() =>
  import("../conversation/workspace/ArtifactDock").then((module) => ({ default: module.ArtifactDock })),
);

export type { DockShowToast };

export function DockSuspense({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingState label="�������빤��̨" />}>{children}</Suspense>;
}

export function ArtifactsDockContent({ conversationId }: { conversationId: string }) {
  const viewModel = useConversationViewModel(conversationId);
  const {
    detail,
    items,
    artifacts,
    openConversation,
    selectArtifact,
    loadRunArtifacts,
  } = viewModel;
  const pendingRevealArtifactIdRef = useRef<string | null>(null);

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
      for (const artifactRef of item.payload.artifact_refs) artifactIds.add(artifactRef.artifact_id);
      refsByRun.set(item.run_id, artifactIds);
    }
    return new Map([...refsByRun].map(([runId, artifactIds]) => [runId, [...artifactIds]]));
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
  useEffect(() => {
    const artifactId = pendingRevealArtifactIdRef.current;
    if (!artifactId || !primaryArtifacts.some((artifact) => artifact.id === artifactId)) return;
    pendingRevealArtifactIdRef.current = null;
  }, [primaryArtifacts]);

  const handleSelectArtifact = (artifactId: string) => {
    if (!primaryArtifacts.some((artifact) => artifact.id === artifactId)) {
      const runId = runIdByArtifactId.get(artifactId);
      if (runId) {
        pendingRevealArtifactIdRef.current = artifactId;
        void loadRunArtifacts(conversationId, runId, [artifactId]).catch(() => {
          if (pendingRevealArtifactIdRef.current === artifactId) pendingRevealArtifactIdRef.current = null;
        });
      }
    }
    void selectArtifact(conversationId, artifactId);
  };

  if (!conversationId || artifacts.filter(isPrimaryConversationArtifact).length === 0) {
    return (
      <EmptyState
        title="���޹���"
        description="������ɺ����ɵĽ����ͼ���ͱʼǻ���������"
      />
    );
  }

  return (
    <ArtifactDock
      artifacts={artifacts}
      selectedArtifactId={detail?.selected_artifact_id}
      onSelectArtifact={handleSelectArtifact}
      onOpenArtifact={(artifact) => openArtifactDock(artifact)}
    />
  );
}

export function ArtifactDockContent({
  tab,
  showToast,
  onAsk,
}: {
  tab: WorkspaceDockTab;
  showToast: DockShowToast;
  onAsk: (reference: import("../../../../sdk/frontend/index").WorkbenchReference) => void;
}) {
  const artifactId = tab.target?.type === "artifact" ? tab.target.id : "";
  const artifact = useConversationStore((s) => s.artifactsById[artifactId]);
  const updateDockTab = useWorkspaceStore((s) => s.updateDockTab);

  if (!artifact) {
    return (
      <WorkspaceShell
        title={tab.title}
        description="�ñ�ǩ�����ù������ݣ���������ע�����ͼ�����ȡ��"
        showHeader={false}
        aria-label={tab.title}
        bodyClassName="workspace-shell__body--artifact"
      >
        <EmptyState
          title="����������"
          description="�ù����ѹرջ�δ�ڵ�ǰ�Ự�����롣"
        />
      </WorkspaceShell>
    );
  }

  const envelope = toArtifactEnvelope(artifact);

  return (
    <WorkspaceShell
      title={artifact.title}
      description="ͬһ�;ù����ڹ������еĽ�����ͼ��"
      showHeader={false}
      aria-label={artifact.title}
      bodyClassName="workspace-shell__body--artifact"
    >
      <div className="workspace-artifact-context-action">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            onAsk({
              label: artifact.title,
              object: { kind: "artifact", id: artifact.id, version: artifact.version },
              artifactId: artifact.id,
            });
            showToast("�Ѽ���Ի�������", "success");
          }}
        >
          <MessageSquarePlus size={14} aria-hidden="true" />
          ����Ի�������
        </Button>
      </div>
      <ArtifactViewHost
        artifact={envelope}
        surface="workspace"
        onToast={showToast}
        selectedViewId={tab.selectedViewId}
        onSelectedViewChange={(selectedViewId) => updateDockTab(tab.viewKey, { selectedViewId })}
        resolveArtifact={(relatedId) => {
            const related = useConversationStore.getState().artifactsById[relatedId];
            return related ? toArtifactEnvelope(related) : null;
        }}
        openArtifact={(value) => {
            const canonical = useConversationStore.getState().artifactsById[value.id];
            if (canonical) openArtifactDock(canonical);
        }}
      />
    </WorkspaceShell>
  );
}

