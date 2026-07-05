import { useState } from "react";
import type { WorkspaceTab } from "../../types/workspace";
import { SmartQueryHome } from "../workspace/SmartQueryHome";
import { ConversationHistoryPanel } from "../conversation/ConversationHistoryPanel";
import { ConversationWorkspace } from "../conversation/workspace/ConversationWorkspace";
import { TableWorkspace } from "../workspace/TableWorkspace";
import { SqlConsoleWorkspace, type ConsoleEntry } from "../workspace/SqlConsoleWorkspace";
import { MultiTableWorkspace } from "../workspace/MultiTableWorkspace";
import { TableArtifactView } from "../workspace/artifacts/TableArtifactView";
import { AgentEvalPage } from "../../pages/AgentEvalPage";
import { DataSourcesPage } from "../../pages/DataSourcesPage";
import { DiagnosticsPage } from "../../pages/DiagnosticsPage";
import { useApiConfig } from "../../components/SettingsDialog";
import { LlmConfigPanel } from "../../components/LlmConfigPanel";
import { testLlmConnection } from "../../lib/api/agent";
import { buildLlmTestValues } from "../../lib/llmConfig";
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

export function WorkspaceRouter({ activeTab, showToast }: WorkspaceRouterProps) {
  if (activeTab.type === "smart-query") {
    return <SmartQueryHomeTab showToast={showToast} />;
  }
  if (activeTab.type === "conversation-history") {
    return <ConversationHistoryTab activeTab={activeTab} />;
  }
  if (activeTab.type === "table") {
    return <TableWorkspaceTab activeTab={activeTab} showToast={showToast} />;
  }
  if (activeTab.type === "sql") {
    return <SqlConsoleTab activeTab={activeTab} showToast={showToast} />;
  }
  if (activeTab.type === "multi-table") {
    return <MultiTableWorkspace tables={activeTab.selectedTables || []} onOpenQueryResult={openQueryResult} onToast={showToast} />;
  }
  if (activeTab.type === "llm-config") {
    return <LlmConfigTabContent activeTab={activeTab} showToast={showToast} />;
  }
  if (activeTab.type === "agent-eval") {
    return <AgentEvalTab showToast={showToast} />;
  }
  if (activeTab.type === "diagnostics") {
    return <DiagnosticsTab activeTab={activeTab} showToast={showToast} />;
  }
  if (activeTab.type === "datasource-settings") {
    return <DatasourceSettingsTab activeTab={activeTab} showToast={showToast} />;
  }
  if (activeTab.type === "artifact-result") {
    return <ArtifactResultTab activeTab={activeTab} showToast={showToast} />;
  }
  return <QueryResultTab activeTab={activeTab} />;
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
    <WorkspaceShell title={activeTab.title} description="管理桌面端可用的数据源连接、健康状态和 schema 同步。">
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

// ── LlmConfigTab ──
function LlmConfigTabContent({ activeTab, showToast }: { activeTab: WorkspaceTab; showToast: (msg: string) => void }) {
  const { config, updateConfig, handleSave } = useApiConfig();

  return (
    <WorkspaceShell title={activeTab.title} description="配置桌面端智能问数使用的模型接口。">
      <LlmConfigPanel
        chrome="workspace"
        variant="page"
        config={config}
        onChange={updateConfig}
        onSave={() => {
          handleSave();
          showToast("LLM 配置保存成功");
        }}
        onTestConnection={async () => {
          showToast("正在测试与模型接口握手…");
          try {
            const llm = buildLlmTestValues(config);
            const result = await testLlmConnection(
              llm.apiKey,
              llm.apiBase,
              llm.modelName,
            );
            if (result.ok) {
              showToast(`连接测试通过 (${result.latency_ms}ms)，模型 ${result.model} 可达`);
            } else {
              showToast(`连接失败 [${result.error_code || "UNKNOWN"}]: ${result.error_message || "未知错误"}`);
            }
          } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : "无法连接到引擎服务，请确认引擎正在运行。";
            showToast(`连接测试失败: ${msg}`);
          }
        }}
      />
    </WorkspaceShell>
  );
}
