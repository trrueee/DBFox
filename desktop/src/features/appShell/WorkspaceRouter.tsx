import React from "react";
import type { WorkspaceTab } from "../../mock/databoxMock";
import type { Conversation } from "../../types/conversation";
import type { DataSource, DataSourceActions } from "../../lib/api/types";
import type { SqlConsoleTabState } from "../workspace/SqlConsoleWorkspace";
import { SmartQueryHome } from "../workspace/SmartQueryHome";
import { ConversationHistoryPanel } from "../conversation/ConversationHistoryPanel";
import { TableWorkspace } from "../workspace/TableWorkspace";
import { SqlConsoleWorkspace } from "../workspace/SqlConsoleWorkspace";
import { MultiTableWorkspace } from "../workspace/MultiTableWorkspace";
import { AgentEvalPage } from "../../pages/AgentEvalPage";
import { DataSourcesPage } from "../../pages/DataSourcesPage";
import { QueryResultWorkspace } from "../workspace/QueryResultWorkspace";
import { useApiConfig } from "../../components/SettingsDialog";
import { LlmConfigPanel } from "../../components/LlmConfigPanel";
import { testLlmConnection } from "../../lib/api/agent";
import { defaultSql } from "../../mock/databoxMock";

interface WorkspaceRouterProps {
  activeTab: WorkspaceTab;
  askInputValue: string;
  onAskInputChange: (val: string) => void;
  contextTables: string[];
  onAddContextTable: (tableName: string) => void;
  onRemoveContextTable: (tableName: string) => void;
  onClearContextTables: () => void;
  openQueryResultTab: (queryText: string) => void;
  conversations: Conversation[];
  openConversationResult: (conversation: Conversation) => void;
  deleteConversationById: (conversationId: string) => void;
  tableSubTabs: Record<string, string>;
  setTableSubTabs: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  openSqlConsole: (initialSql?: string) => void;
  showToast: (msg: string) => void;
  sqlConsoleState: Record<string, SqlConsoleTabState>;
  setSqlConsoleState: React.Dispatch<React.SetStateAction<Record<string, SqlConsoleTabState>>>;
  datasources: DataSource[];
  activeDatasourceId: string;
  setActiveDatasourceId: (id: string) => void;
  activeDatasourceForSettings: DataSource | null;
  loadDatasources: (preferredId?: string) => Promise<void>;
  sendFollowUp: (tabId: string, text: string) => void;
  handleApprovalDecision: (tabId: string, approved: boolean) => Promise<void>;
  cancelAgentRun: (tabId: string) => Promise<void>;
  regenerateAgentRun: (tabId: string) => void;
  datasourceActions?: DataSourceActions;
}

export function WorkspaceRouter({
  activeTab,
  askInputValue,
  onAskInputChange,
  contextTables,
  onAddContextTable,
  onRemoveContextTable,
  onClearContextTables,
  openQueryResultTab,
  conversations,
  openConversationResult,
  deleteConversationById,
  tableSubTabs,
  setTableSubTabs,
  openSqlConsole,
  showToast,
  sqlConsoleState,
  setSqlConsoleState,
  datasources,
  activeDatasourceId,
  setActiveDatasourceId,
  activeDatasourceForSettings,
  loadDatasources,
  sendFollowUp,
  handleApprovalDecision,
  cancelAgentRun,
  regenerateAgentRun,
  datasourceActions,
}: WorkspaceRouterProps) {
  if (activeTab.type === "smart-query") {
    return (
      <SmartQueryHome
        askInputValue={askInputValue}
        contextTables={contextTables}
        onAskInputChange={onAskInputChange}
        onSubmitAsk={() => openQueryResultTab(askInputValue)}
        onAddContextTable={onAddContextTable}
        onRemoveContextTable={onRemoveContextTable}
        onClearContextTables={onClearContextTables}
      />
    );
  }
  if (activeTab.type === "conversation-history") {
    return (
      <ConversationHistoryPanel
        conversations={conversations}
        activeConversationId={activeTab.conversationId}
        onOpenConversation={openConversationResult}
        onDeleteConversation={deleteConversationById}
      />
    );
  }
  if (activeTab.type === "table") {
    const tableId = activeTab.tableId || "id_users";
    return (
      <TableWorkspace
        tableId={tableId}
        currentSubTab={tableSubTabs[tableId] || "preview"}
        onSubTabChange={(subTab) => setTableSubTabs((prev) => ({ ...prev, [tableId]: subTab }))}
        onOpenSqlConsole={openSqlConsole}
        onToast={showToast}
      />
    );
  }
  if (activeTab.type === "sql") {
    const tabState = sqlConsoleState[activeTab.id] ?? { draftSql: defaultSql, entries: [], running: false };
    return (
      <SqlConsoleWorkspace
        tabId={activeTab.id}
        state={tabState}
        onPatchState={(id, patch) => setSqlConsoleState((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }))}
        onAppendEntries={(id, newEntries) =>
          setSqlConsoleState((prev) => ({
            ...prev,
            [id]: { ...prev[id], entries: [...(prev[id]?.entries ?? []), ...newEntries] },
          }))
        }
        onToast={showToast}
        datasources={datasources}
        activeDatasourceId={activeDatasourceId}
      />
    );
  }
  if (activeTab.type === "multi-table") {
    return <MultiTableWorkspace tables={activeTab.selectedTables || []} onOpenQueryResult={openQueryResultTab} onToast={showToast} />;
  }
  if (activeTab.type === "llm-config") {
    return <LlmConfigTabContent showToast={showToast} />;
  }
  if (activeTab.type === "agent-eval") {
    return (
      <AgentEvalPage
        datasources={datasources}
        activeDatasourceId={activeDatasourceId}
        onToast={showToast}
      />
    );
  }
  if (activeTab.type === "datasource-settings") {
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
          actions={datasourceActions}
        />
      </div>
    );
  }
  return (
    <QueryResultWorkspace
      tab={activeTab}
      onOpenSqlConsole={openSqlConsole}
      onSendFollowUp={sendFollowUp}
      onApproveAgent={(tabId) => void handleApprovalDecision(tabId, true)}
      onRejectAgent={(tabId) => void handleApprovalDecision(tabId, false)}
      onCancelRun={cancelAgentRun}
      onRegenerateRun={regenerateAgentRun}
      onToast={showToast}
    />
  );
}

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
              showToast(
                `连接测试通过 (${result.latency_ms}ms)，模型 ${result.model} 可达`,
              );
            } else {
              showToast(
                `连接失败 [${result.error_code || "UNKNOWN"}]: ${result.error_message || "未知错误"}`,
              );
            }
          } catch (e: unknown) {
            const msg =
              e instanceof Error ? e.message : "无法连接到引擎服务，请确认引擎正在运行。";
            showToast(`连接测试失败: ${msg}`);
          }
        }}
      />
    </div>
  );
}
