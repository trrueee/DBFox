import { lazy, Suspense, useEffect, useMemo, useRef } from "react";
import { EmptyState, LoadingState } from "../../components/ui";
import { useArtifactDockStore } from "../../stores/artifactDockStore";
import { useConversationViewModel } from "../conversation/workspace/useConversationViewModel";
import { isPrimaryConversationArtifact } from "../conversation/workspace/conversationArtifactModels";
import {
  createArtifactRendererRegistry,
  productArtifactRenderers,
  renderArtifact,
  type ArtifactEnvelope,
} from "../workspace/artifacts/artifactRendererRegistry";
import { WorkspaceShell } from "./WorkspaceShell";
import type { WorkspaceDockTab } from "../../types/workspace";
import type { DockShowToast } from "../dock/types";

const ArtifactDock = lazy(() =>
  import("../conversation/workspace/ArtifactDock").then((module) => ({ default: module.ArtifactDock })),
);

export type { DockShowToast };

export function DockSuspense({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingState label="正在载入工作台" />}>{children}</Suspense>;
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
  const openDockArtifact = useArtifactDockStore((s) => s.openArtifact);
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
        title="暂无工件"
        description="AI 完成分析后，查询结果、图表和笔记会出现在这里。"
      />
    );
  }

  return (
    <ArtifactDock
      artifacts={artifacts}
      selectedArtifactId={detail?.selected_artifact_id}
      onSelectArtifact={handleSelectArtifact}
      onOpenResultTab={(artifact) => openDockArtifact(artifact, conversationId)}
    />
  );
}

export function ArtifactDockContent({
  tab,
  showToast,
}: {
  tab: WorkspaceDockTab;
  showToast: DockShowToast;
}) {
  const artifactId = tab.target?.type === "artifact" ? tab.target.id : "";
  const artifact = useArtifactDockStore((s) => s.artifactById[artifactId]);
  const conversationId = useArtifactDockStore((s) => s.conversationIdByArtifactId[artifactId]);

  const rendererRegistry = useMemo(
    () =>
      createArtifactRendererRegistry(
        productArtifactRenderers({
          dataActions: {
            onOpenResultTab: (value) => {
              useArtifactDockStore.getState().openArtifact(value, conversationId);
            },
          },
        }),
      ),
    [conversationId],
  );

  if (!artifact) {
    return (
      <WorkspaceShell
        title={tab.title}
        description="基于工件 ID 实时分页查询，当前表格不是历史结果快照。"
        bodyClassName="workspace-shell__body--artifact-result"
      >
        <EmptyState
          title="工件不可用"
          description="该工件已关闭或未在当前会话中载入。"
        />
      </WorkspaceShell>
    );
  }

  const envelope: ArtifactEnvelope = {
    id: artifact.id,
    type: artifact.type,
    schema_version: artifact.schemaVersion ?? 1,
    title: artifact.title,
    payload: {
      sourceSqlArtifactId: artifact.sourceSqlArtifactId,
      queryFingerprint: artifact.queryFingerprint,
      datasourceGeneration: artifact.datasourceGeneration,
      columns: artifact.columns,
      rowCount: artifact.rowCount,
      returnedRows: artifact.returnedRows,
      latencyMs: artifact.latencyMs,
      truncated: artifact.truncated,
    },
  };

  return (
    <WorkspaceShell
      title={artifact.title}
      description="基于工件 ID 实时分页查询，当前表格不是历史结果快照。"
      bodyClassName="workspace-shell__body--artifact-result"
    >
      {renderArtifact(
        envelope,
        {
          onToast: showToast,
          mode: "workspace",
        },
        rendererRegistry,
      )}
    </WorkspaceShell>
  );
}
