import { lazy, Suspense, useEffect, useMemo, useRef } from "react";
import { EmptyState, LoadingState } from "../../components/ui";
import { useDatasourceState } from "../datasource/useDatasourceState";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { defaultSql } from "../workspace/defaultSql";
import type { ConsoleEntry } from "../workspace/SqlConsoleWorkspace";
import { useConversationViewModel } from "../conversation/workspace/useConversationViewModel";
import { isPrimaryConversationArtifact } from "../conversation/workspace/conversationArtifactModels";
import { renderArtifact, type ArtifactEnvelope } from "../workspace/artifacts/artifactRendererRegistry";
import { WorkspaceShell } from "./WorkspaceShell";
import type { WorkspaceDockTab } from "../../types/workspace";

const SqlConsoleWorkspace = lazy(() =>
  import("../workspace/SqlConsoleWorkspace").then((module) => ({ default: module.SqlConsoleWorkspace })),
);
const TableWorkspace = lazy(() =>
  import("../workspace/TableWorkspace").then((module) => ({ default: module.TableWorkspace })),
);
const ArtifactDock = lazy(() =>
  import("../conversation/workspace/ArtifactDock").then((module) => ({ default: module.ArtifactDock })),
);

export type DockShowToast = (
  message: string,
  type?: "success" | "error" | "warning" | "info",
) => void;

export function DockSuspense({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingState label="正在载入工作台" />}>{children}</Suspense>;
}

export function ConsoleDockContent({
  tab,
  activeDatasourceId,
  showToast,
}: {
  tab: WorkspaceDockTab;
  activeDatasourceId: string;
  showToast: DockShowToast;
}) {
  const { datasources } = useDatasourceState();
  const sqlConsoleState = useWorkspaceStore((s) => s.sqlConsoleState);
  const patchSqlConsoleState = useWorkspaceStore((s) => s.patchSqlConsoleState);
  const appendSqlConsoleEntries = useWorkspaceStore((s) => s.appendSqlConsoleEntries);
  const tabId = tab.stateKey ?? `sql-${tab.datasourceId}`;
  const state = sqlConsoleState[tabId] ?? { draftSql: defaultSql, entries: [], running: false };

  return (
    <SqlConsoleWorkspace
      tabId={tabId}
      state={state}
      onPatchState={(id, patch) => patchSqlConsoleState(id, patch)}
      onAppendEntries={(id, newEntries: ConsoleEntry[]) => appendSqlConsoleEntries(id, newEntries)}
      onToast={showToast}
      datasources={datasources}
      activeDatasourceId={tab.datasourceId || activeDatasourceId}
    />
  );
}

export function TableDockContent({
  tab,
  showToast,
}: {
  tab: WorkspaceDockTab;
  showToast: DockShowToast;
}) {
  const tableSubTabs = useWorkspaceStore((s) => s.tableSubTabs);
  const setTableSubTabs = useWorkspaceStore((s) => s.setTableSubTabs);
  const openDockConsole = useWorkspaceStore((s) => s.openDockConsole);
  const tableId = tab.tableId ?? "";
  const datasourceId = tab.datasourceId ?? "";
  const subTabKey = tab.id || tableId;

  return (
    <TableWorkspace
      key={tab.id}
      tableId={tableId}
      datasourceId={datasourceId}
      datasourceDbType={tab.datasourceDbType}
      currentSubTab={tableSubTabs[subTabKey] || tableSubTabs[tableId] || "preview"}
      onSubTabChange={(subTab) => setTableSubTabs((prev) => ({ ...prev, [subTabKey]: subTab }))}
      onOpenSqlConsole={(initialSql) => openDockConsole(datasourceId, tab.datasourceDbType, initialSql)}
      onToast={showToast}
    />
  );
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
  const openDockArtifact = useWorkspaceStore((s) => s.openDockArtifact);
  const openDockConsole = useWorkspaceStore((s) => s.openDockConsole);
  const { activeDatasource } = useDatasourceState();
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
      onOpenSqlConsole={(sql) => {
        if (!activeDatasource) return;
        openDockConsole(activeDatasource.id, activeDatasource.db_type, sql);
      }}
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
  const artifact = tab.artifact;
  if (!artifact) return null;
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
      {renderArtifact(envelope, {
        onToast: showToast,
        mode: "workspace",
        onOpenResultTab: (value) => {
          useWorkspaceStore.getState().openDockArtifact(value, tab.conversationId);
        },
      })}
    </WorkspaceShell>
  );
}
