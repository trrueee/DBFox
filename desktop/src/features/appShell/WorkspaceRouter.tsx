import { useState } from "react";
import type { WorkspaceTab } from "../../mock/dbfoxMock";
import { SmartQueryHome } from "../workspace/SmartQueryHome";
import { ConversationHistoryPanel } from "../conversation/ConversationHistoryPanel";
import { ConversationWorkspace } from "../conversation/workspace/ConversationWorkspace";
import { TableWorkspace } from "../workspace/TableWorkspace";
import { SqlConsoleWorkspace, type ConsoleEntry } from "../workspace/SqlConsoleWorkspace";
import { MultiTableWorkspace } from "../workspace/MultiTableWorkspace";
import { AgentEvalPage } from "../../pages/AgentEvalPage";
import { DataSourcesPage } from "../../pages/DataSourcesPage";
import { DiagnosticsPage } from "../../pages/DiagnosticsPage";
import { useApiConfig } from "../../components/SettingsDialog";
import { LlmConfigPanel } from "../../components/LlmConfigPanel";
import { testLlmConnection } from "../../lib/api/agent";
import { defaultSql } from "../../mock/dbfoxMock";
import { useWorkspaceStore } from "../../stores/workspaceStore";
import { useDatasourceStore } from "../../stores/datasourceStore";
import { useConversationStore } from "../../stores/conversationStore";
import type { ConversationSummary } from "../../types/conversation";

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
    return <LlmConfigTabContent showToast={showToast} />;
  }
  if (activeTab.type === "agent-eval") {
    return <AgentEvalTab showToast={showToast} />;
  }
  if (activeTab.type === "diagnostics") {
    return <DiagnosticsTab showToast={showToast} />;
  }
  if (activeTab.type === "datasource-settings") {
    return <DatasourceSettingsTab activeTab={activeTab} showToast={showToast} />;
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

  return (
    <TableWorkspace
      tableId={tableId}
      datasourceId={activeDatasourceId || ""}
      currentSubTab={tableSubTabs[tableId] || "preview"}
      onSubTabChange={(subTab) => setTableSubTabs((prev) => ({ ...prev, [tableId]: subTab }))}
      onOpenSqlConsole={openSqlConsole}
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
      activeDatasourceId={activeDatasourceId}
    />
  );
}

// ── AgentEval tab ──
function AgentEvalTab({ showToast }: { showToast: WorkspaceRouterProps["showToast"] }) {
  const datasources = useDatasourceStore((s) => s.datasources);
  const activeDatasourceId = useDatasourceStore((s) => s.activeDatasourceId);
  return <AgentEvalPage datasources={datasources} activeDatasourceId={activeDatasourceId} onToast={showToast} />;
}

function DiagnosticsTab({ showToast }: { showToast: WorkspaceRouterProps["showToast"] }) {
  return (
    <div className="hifi-settings-tab-frame">
      <DiagnosticsPage onToast={showToast} />
    </div>
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
    <div className="hifi-settings-tab-frame">
      <DataSourcesPage
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
    </div>
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
      onDelete={() => {
        if (conversationId) void useConversationStore.getState().deleteConversationById(conversationId);
        useWorkspaceStore.getState().closeTab(activeTab.id);
      }}
    />
  );
}

// ── Shared helpers ──
function openQueryResult(queryText: string) {
  const text = queryText.trim();
  if (!text) return;
  useWorkspaceStore.getState().openQueryResultTab(text);
}

// ── LlmConfigTab ──
function LlmConfigTabContent({ showToast }: { showToast: (msg: string) => void }) {
  const { config, updateConfig, handleSave } = useApiConfig();

  return (
    <div className="hifi-settings-tab-frame">
      <LlmConfigPanel
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
            const result = await testLlmConnection(
              config.apiKey || "",
              config.apiBase || "https://api.openai.com/v1",
              config.modelName || "gpt-4o-mini",
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
    </div>
  );
}
