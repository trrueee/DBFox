import { lazy, useEffect, useMemo, useRef, useState } from "react";
import {
  AtIcon,
  CheckIcon,
} from "@/components/icons";
import { Button, EmptyState, LoadingState, Tooltip, TooltipTrigger, TooltipContent } from "../../components/ui";
import { openArtifactDock } from "../../stores/artifactDockStore";
import { useConversationStore } from "../../stores/conversationStore";
import { selectActiveWorkbenchReferences, useWorkspaceStore } from "../../stores/workspaceStore";
import { useConversationViewModel } from "../conversation/workspace/useConversationViewModel";
import { isPrimaryConversationArtifact } from "../conversation/workspace/conversationArtifactSelectors";
import { ArtifactViewHost } from "../workspace/artifacts/ArtifactViewHost";
import { WorkspaceShell } from "../workspace/WorkspaceShell";
import type { WorkspaceDockTab } from "../../types/workspace";
import type { DockShowToast } from "./types";
import { toArtifactEnvelope } from "../workspace/artifacts/artifactEnvelope";
import { getRuntimeSession } from "../../lib/api/client";

const ArtifactDock = lazy(() =>
  import("../conversation/workspace/ArtifactDock").then((module) => ({ default: module.ArtifactDock })),
);

export type { DockShowToast };

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
        title="暂无工件"
        description="分析完成后生成的结果、图表和笔记会显示在这里。"
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
  const referenced = useWorkspaceStore(state => selectActiveWorkbenchReferences(state).some(reference => reference.artifactId === artifactId));
  const artifact = useConversationStore((s) => s.artifactsById[artifactId]);
  const loadArtifact = useConversationStore((s) => s.loadArtifact);
  const updateDockTab = useWorkspaceStore((s) => s.updateDockTab);
  const activeProjectId = useWorkspaceStore((s) => s.activeProjectId);
  const projectId = tab.projectId ?? activeProjectId;
  const [loadFailed, setLoadFailed] = useState(false);
  const [readAttempt, setReadAttempt] = useState(0);

  useEffect(() => {
    if (artifact || !artifactId || !projectId) return;
    const controller = new AbortController();
    const generation = getRuntimeSession().generation;
    void loadArtifact(projectId, artifactId, {
      signal: controller.signal,
      beforeCommit: () => {
        controller.signal.throwIfAborted();
        if (generation !== getRuntimeSession().generation
          || useWorkspaceStore.getState().activeProjectId !== projectId) {
          throw new Error("Artifact read is no longer active in this project.");
        }
      },
    }).catch(() => {
      if (!controller.signal.aborted) setLoadFailed(true);
    });
    return () => controller.abort();
  }, [artifact, artifactId, projectId, loadArtifact, readAttempt]);

  if (!artifact) {
    return (
      <WorkspaceShell
        title={tab.title}
        description="此标签引用工件，内容由已注册的视图负责读取。"
        showHeader={false}
        aria-label={tab.title}
        bodyClassName="workspace-shell__body--artifact"
      >
        {loadFailed || !artifactId || !projectId ? (
          <div>
            <EmptyState
              title="无法载入成果"
              description="请确认成果仍属于当前项目，或重试读取。"
            />
            <Button variant="outline" size="sm" onClick={() => {
              setLoadFailed(false);
              setReadAttempt((attempt) => attempt + 1);
            }}>
              重试
            </Button>
          </div>
        ) : <LoadingState label="正在读取成果" />}
      </WorkspaceShell>
    );
  }

  const envelope = toArtifactEnvelope(artifact);

  return (
    <WorkspaceShell
      title={artifact.title}
      description="同一工件在工作区中的交互视图。"
      showHeader={false}
      aria-label={artifact.title}
      bodyClassName="workspace-shell__body--artifact"
    >
      <div className="workspace-artifact-context-action">
        <Tooltip><TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={referenced ? "已加入对话上下文" : "加入对话上下文"}
          disabled={referenced}
          onClick={() => {
            onAsk({
              label: artifact.title,
              artifactId: artifact.id,
            });
          }}
        >
          {referenced ? <CheckIcon size={20} aria-hidden="true" /> : <AtIcon size={20} aria-hidden="true" />}
        </Button>
        </TooltipTrigger><TooltipContent>{referenced ? "已加入对话上下文" : "加入对话上下文"}</TooltipContent></Tooltip>
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
            openArtifactDock(canonical ?? value);
        }}
      />
    </WorkspaceShell>
  );
}

