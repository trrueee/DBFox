import { lazy, Suspense, useState, type ReactNode } from "react";
import type { WorkspaceTab } from "../../types/workspace";
import type { ConsoleEntry } from "../workspace/SqlConsoleWorkspace";
import { defaultSql } from "../workspace/defaultSql";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { useConversationStore } from "../../stores/conversationStore";
import type { ConversationSummary } from "../../types/conversation";
import { WorkspaceShell } from "./WorkspaceShell";

interface WorkspaceRouterProps {
  activeTab: WorkspaceTab;
  showToast: (msg: string, type?: "success" | "error" | "warning" | "info") => void;
}

const SmartQueryHome = lazy(async () => {
  const module = await import("../workspace/SmartQueryHome");
  return { default: module.SmartQueryHome };
});
const ConversationHistoryPanel = lazy(async () => {
  const module = await import("../conversation/ConversationHistoryPanel");
  return { default: module.ConversationHistoryPanel };
});
const ConversationWorkspace = lazy(async () => {
  const module = await import("../conversation/workspace/ConversationWorkspace");
  return { default: module.ConversationWorkspace };
});
const TableWorkspace = lazy(async () => {
  const module = await import("../workspace/TableWorkspace");
  return { default: module.TableWorkspace };
});
const SqlConsoleWorkspace = lazy(async () => {
  const module = await import("../workspace/SqlConsoleWorkspace");
  return { default: module.SqlConsoleWorkspace };
});
const MultiTableWorkspace = lazy(async () => {
  const module = await import("../workspace/MultiTableWorkspace");
  return { default: module.MultiTableWorkspace };
});
const TableArtifactView = lazy(async () => {
  const module = await import("../workspace/artifacts/TableArtifactView");
  return { default: module.TableArtifactView };
});
const AgentEvalPage = lazy(async () => {
  const module = await import("../../pages/AgentEvalPage");
  return { default: module.AgentEvalPage };
});
const DataSourcesPage = lazy(async () => {
  const module = await import("../../pages/DataSourcesPage");
  return { default: module.DataSourcesPage };
});
const DiagnosticsPage = lazy(async () => {
  const module = await import("../../pages/DiagnosticsPage");
  return { default: module.DiagnosticsPage };
});
const LlmConfigWorkspaceTab = lazy(async () => {
  const module = await import("./LlmConfigWorkspaceTab");
  return { default: module.LlmConfigWorkspaceTab };
});

function WorkspaceRouteBoundary({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="workspace-route-loading" role="status">正在载入工作区…</div>}>
      {children}
    </Suspense>
  );
}

export function WorkspaceRouter({ activeTab, showToast }: WorkspaceRouterProps) {
  if (activeTab.type === "smart-query") {
    return <WorkspaceRouteBoundary><SmartQueryHomeTab showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "conversation-history") {
    return <WorkspaceRouteBoundary><ConversationHistoryTab activeTab={activeTab} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "table") {
    return <WorkspaceRouteBoundary><TableWorkspaceTab activeTab={activeTab} showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "sql") {
    return <WorkspaceRouteBoundary><SqlConsoleTab activeTab={activeTab} showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "multi-table") {
    return (
      <WorkspaceRouteBoundary>
        <MultiTableWorkspace tables={activeTab.selectedTables || []} onOpenQueryResult={openQueryResult} onToast={showToast} />
      </WorkspaceRouteBoundary>
    );
  }
  if (activeTab.type === "llm-config") {
    return <WorkspaceRouteBoundary><LlmConfigWorkspaceTab activeTab={activeTab} showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "agent-eval") {
    return <WorkspaceRouteBoundary><AgentEvalTab showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "diagnostics") {
    return <WorkspaceRouteBoundary><DiagnosticsTab activeTab={activeTab} showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "datasource-settings") {
    return <WorkspaceRouteBoundary><DatasourceSettingsTab activeTab={activeTab} showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  if (activeTab.type === "artifact-result") {
    return <WorkspaceRouteBoundary><ArtifactResultTab activeTab={activeTab} showToast={showToast} /></WorkspaceRouteBoundary>;
  }
  return <WorkspaceRouteBoundary><QueryResultTab activeTab={activeTab} /></WorkspaceRouteBoundary>;
}

// ── SmartQueryHome tab ──
function SmartQueryHomeTab({ showToast }: { showToast: WorkspaceRouterProps["showToast"] }) {
  const [askInputValue, setAskInputValue] = useState("");
  const contextTables = useWorkspaceStore((s) => s.contextTables);
  const addContextTable = useWorkspaceStore((s) => s.addContextTable);
  const removeContextTable = useWorkspaceStore((s) => s.removeContextTable);
  const clearContextTables = useWorkspaceStore((s) => s.clearContextTables);

  const handleSubmitAsk = async () => {
    const text = askInputValue.trim();
    if (!text) return;
    setAskInputValue("");
    try {
      const detail = await useConversationStore.getState().createAndOpenConversation(text, contextTables);
      useWorkspaceStore.getState().openConversationResult({ id: detail.id, title: detail.title });
      void useConversationStore
        .getState()
        .sendMessage(detail.id, text)
        .catch((error) => showToast(error instanceof Error ? error.message : "执行失败", "error"));
    } catch (error) {
      showToast(error instanceof Error ? error.message : "创建会话失败", "error");
    }
  };

  return (
    <SmartQueryHome
      askInputValue={askInputValue}
      contextTables={contextTables}
      onAskInputChange={setAskInputValue}
      onSubmitAsk={handleSubmitAsk}
      onAddContextTable={addContextTable}
      onRemoveContextTable={removeContextTable}
      onClearContextTables={clearContextTables}
    />
  );
}

// ── ConversationHistory tab ──
function ConversationHistoryTab({ activeTab }: { activeTab: WorkspaceTab }) {
  const conversations = useConversationStore((s) => s.summaries);
  const openConversation = async (summary: ConversationSummary) => {
    await useConversationStore.getState().openConversation(summary.id);
    useWorkspaceStore.getState().openConversationResult({ id: summary.id, title: summary.title });
  };

  return (
    <ConversationHistoryPanel
      conversations={conversations}
      activeConversationId={activeTab.conversationId}
      onOpenConversation={(summary) => void openConversation(summary)}
      onDeleteConversation={(conversationId) => void useConversationStore.getState().deleteConversationById(conversationId)}
    />
  );
}

// ── TableWorkspace tab ──
function TableWorkspaceTab({ activeTab, showToast }: { activeTab: WorkspaceTab; showToast: WorkspaceRouterProps["showToast"] }) {
  const tableId = activeTab.tableId || "";
  const tableSubTabs = useWorkspaceStore((s) => s.tableSubTabs);
  const setTableSubTabs = useWorkspaceStore((s) => s.setTableSubTabs);
  const openSqlConsole = useWorkspaceStore((s) => s.openSqlConsole);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  const datasources = useDatasourceStore((s) => s.datasources);
  const fallbackDatasource = datasources.find((item) => item.id === activeDatasourceId) ?? datasources[0] ?? null;
  const tabDatasource = activeTab.datasourceId
    ? datasources.find((item) => item.id === activeTab.datasourceId) ?? null
    : null;
  const datasourceId = activeTab.datasourceId || activeDatasourceId || fallbackDatasource?.id || "";
  const datasourceDbType = activeTab.datasourceDbType ?? tabDatasource?.db_type ?? fallbackDatasource?.db_type ?? null;
  const subTabKey = activeTab.id || tableId;
  const openTableSqlConsole = (initialSql?: string) => {
    openSqlConsole(initialSql, datasourceId, datasourceDbType);
  };

  return (
    <TableWorkspace
      tableId={tableId}
      datasourceId={datasourceId}
      datasourceDbType={datasourceDbType}
      currentSubTab={tableSubTabs[subTabKey] || tableSubTabs[tableId] || "preview"}
      onSubTabChange={(subTab) => setTableSubTabs((prev) => ({ ...prev, [subTabKey]: subTab }))}
      onOpenSqlConsole={openTableSqlConsole}
      onToast={showToast}
    />
  );
}

// ── SqlConsole tab ──
function SqlConsoleTab({ activeTab, showToast }: { activeTab: WorkspaceTab; showToast: WorkspaceRouterProps["showToast"] }) {
  const datasources = useDatasourceStore((s) => s.datasources);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  const sqlConsoleState = useWorkspaceStore((s) => s.sqlConsoleState);
  const tabState = sqlConsoleState[activeTab.id] ?? { draftSql: defaultSql, entries: [], running: false };
  const datasourceId = activeTab.datasourceId || activeDatasourceId;

  const onPatchState = (id: string, patch: Record<string, unknown>) => {
    useWorkspaceStore.setState((s) => ({
      sqlConsoleState: { ...s.sqlConsoleState, [id]: { ...s.sqlConsoleState[id], ...patch } },
    }));
  };

  const onAppendEntries = (id: string, newEntries: ConsoleEntry[]) => {
    useWorkspaceStore.setState((s) => ({
      sqlConsoleState: {
        ...s.sqlConsoleState,
        [id]: { ...s.sqlConsoleState[id], entries: [...(s.sqlConsoleState[id]?.entries ?? []), ...newEntries] },
      },
    }));
  };

  return (
    <SqlConsoleWorkspace
      tabId={activeTab.id}
      state={tabState}
      onPatchState={onPatchState}
      onAppendEntries={onAppendEntries}
      onToast={showToast}
      datasources={datasources}
      activeDatasourceId={datasourceId}
    />
  );
}

// ── AgentEval tab ──
function AgentEvalTab({ showToast }: { showToast: WorkspaceRouterProps["showToast"] }) {
  const datasources = useDatasourceStore((s) => s.datasources);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  return <AgentEvalPage datasources={datasources} activeDatasourceId={activeDatasourceId} onToast={showToast} />;
}

function DiagnosticsTab({ activeTab, showToast }: { activeTab: WorkspaceTab; showToast: WorkspaceRouterProps["showToast"] }) {
  return (
    <WorkspaceShell title={activeTab.title} description="查看本地前端、后端诊断日志和运行环境。">
      <DiagnosticsPage onToast={showToast} chrome="workspace" />
    </WorkspaceShell>
  );
}

// ── DatasourceSettings tab ──
function DatasourceSettingsTab({ activeTab, showToast }: { activeTab: WorkspaceTab; showToast: WorkspaceRouterProps["showToast"] }) {
  const datasources = useDatasourceStore((s) => s.datasources);
  const setActiveDatasourceId = useDatasourceStore((s) => s.setActiveDatasourceId);
  const loadDatasources = useDatasourceStore((s) => s.loadDatasources);
  const activeDatasourceForSettings = useDatasourceStore((s) => s.activeDatasourceForSettings);
  const createDatasource = useDatasourceStore((s) => s.createDatasource);
  const updateDatasource = useDatasourceStore((s) => s.updateDatasource);
  const deleteDatasource = useDatasourceStore((s) => s.deleteDatasource);
  const syncSchema = useDatasourceStore((s) => s.syncSchema);
  const checkHealth = useDatasourceStore((s) => s.checkHealth);

  return (
    <WorkspaceShell title={activeTab.title} description="管理数据源连接、连接状态和表结构同步。">
      <DataSourcesPage
        chrome="workspace"
        onSelectDataSource={(ds) => {
          if (ds) {
            setActiveDatasourceId(ds.id);
            showToast(`已激活数据源: ${ds.name}`);
          } else {
            setActiveDatasourceId("");
          }
        }}
        activeDataSource={activeDatasourceForSettings}
        activeProject={null}
        onRefreshDatasources={loadDatasources}
        initialShowAddForm={activeTab.title === "新建数据源"}
        datasources={datasources}
        actions={{ createDatasource, updateDatasource, deleteDatasource, syncSchema, checkHealth }}
      />
    </WorkspaceShell>
  );
}

// ── QueryResult tab ──
function QueryResultTab({ activeTab }: { activeTab: WorkspaceTab }) {
  const openSqlConsole = useWorkspaceStore((s) => s.openSqlConsole);
  const conversationId = activeTab.conversationId || "";

  return (
    <ConversationWorkspace
      conversationId={conversationId}
      onOpenHistory={() => useWorkspaceStore.getState().openConversationHistoryTab()}
      onOpenSqlConsole={openSqlConsole}
      onOpenResultTab={(artifact) => useWorkspaceStore.getState().openArtifactResultTab(artifact)}
      onDelete={() => {
        if (conversationId) void useConversationStore.getState().deleteConversationById(conversationId);
        useWorkspaceStore.getState().closeTab(activeTab.id);
      }}
    />
  );
}

function ArtifactResultTab({
  activeTab,
  showToast,
}: {
  activeTab: WorkspaceTab;
  showToast: WorkspaceRouterProps["showToast"];
}) {
  if (!activeTab.artifactResult) {
    return (
      <WorkspaceShell
        title={activeTab.title}
        state={{
          kind: "error",
          title: "结果不可用",
          description: "这个结果工件已不在当前会话上下文中。",
        }}
      />
    );
  }
  return (
    <WorkspaceShell
      title={activeTab.title}
      description="查看由智能问数生成的可复用结果工件。"
      bodyClassName="workspace-shell__body--artifact-result"
    >
      <TableArtifactView artifact={activeTab.artifactResult} onToast={showToast} mode="workspace" />
    </WorkspaceShell>
  );
}

// ── Shared helpers ──
function openQueryResult(queryText: string) {
  const text = queryText.trim();
  if (!text) return;
  useWorkspaceStore.getState().openQueryResultTab(text);
}
