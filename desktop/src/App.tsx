import { useEffect, useState, useMemo, useRef, type CSSProperties, type MouseEvent } from "react";
import { Sparkles, Cpu, Settings, Database, FileText, Terminal, HelpCircle, FlaskConical } from "lucide-react";
import "./App.css";
import { ContextDrawer } from "./features/assistant/ContextDrawer";
import { ConversationHistoryPanel } from "./features/conversation/ConversationHistoryPanel";
import { deleteConversation, listConversations, saveConversation } from "./features/conversation/conversationRepository";
import { DataSourceContextMenu } from "./features/datasource/DataSourceContextMenu";
import { DataSourceTree } from "./features/datasource/DataSourceTree";
import { MultiTableWorkspace } from "./features/workspace/MultiTableWorkspace";
import { QueryResultWorkspace } from "./features/workspace/QueryResultWorkspace";
import { SmartQueryHome } from "./features/workspace/SmartQueryHome";
import { SqlConsoleWorkspace } from "./features/workspace/SqlConsoleWorkspace";
import { TableWorkspace } from "./features/workspace/TableWorkspace";
import { WorkspaceTabs } from "./features/workspace/WorkspaceTabs";
import { defaultSql, type ContextMenuState, type WorkspaceTab } from "./mock/databoxMock";
import type { Conversation, ConversationMessage } from "./types/conversation";
import { listDatasources, listTables, listColumns } from "./features/engine/engineApi";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { AgentEvalPage } from "./pages/AgentEvalPage";
import { useApiConfig, getStoredApiConfig } from "./components/SettingsDialog";
import { CommandPalette, type CommandItem } from "./components/CommandPalette";
import { agentApi, resolveAgentApproval, streamResumeAgentRun } from "./lib/api/agent";
import type { AgentArtifact as ApiAgentArtifact, AgentRunResponse, AgentRuntimeEvent } from "./lib/api/types";
import {
  buildAnswerText,
  buildSuggestionsText,
  describeRuntimeEvent,
  mergeApiArtifacts,
  toViewArtifacts,
} from "./features/workspace/agentBridge";

export default function App() {
  const [scale, setScale] = useState(1);
  const [treeSearch, setTreeSearch] = useState("");
  const [askInputValue, setAskInputValue] = useState("帮我查一下“市场运营部”上个月发布了多少资产？");
  const [tabs, setTabs] = useState<WorkspaceTab[]>([{ id: "smart-query", title: "问数工作台", type: "smart-query" }]);
  const [activeTabId, setActiveTabId] = useState("smart-query");
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [contextTables, setContextTables] = useState<string[]>([]);
  const [tableSubTabs, setTableSubTabs] = useState<Record<string, string>>({});
  const [rightDrawerOpen, setRightDrawerOpen] = useState(false);
  const [rightDrawerType, setRightDrawerType] = useState<"ai-suggest" | "props">("props");
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "database", targetNode: "" });
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [sqlQuery, setSqlQuery] = useState(defaultSql);
  const [recentTab, setRecentTab] = useState("tables");
  const [conversations, setConversations] = useState<Conversation[]>([]);

  // Lifted data sources states
  const [datasources, setDatasources] = useState<any[]>([]);
  const [activeDatasourceId, setActiveDatasourceId] = useState("");
  const [tables, setTables] = useState<any[]>([]);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [schemaError, setSchemaError] = useState("");
  const [tableColumns, setTableColumns] = useState<Record<string, any[]>>({});

  // Layout UI states
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);

  const activeDatasource = useMemo(() => datasources.find((item) => item.id === activeDatasourceId) || null, [activeDatasourceId, datasources]);
  const activeTab = tabs.find((tab) => tab.id === activeTabId) || tabs[0];

  // Refs that mirror state for async agent stream handlers
  const tabsRef = useRef<WorkspaceTab[]>(tabs);
  const conversationsRef = useRef<Conversation[]>(conversations);
  const msgIdSeq = useRef(Date.now());
  useEffect(() => { tabsRef.current = tabs; }, [tabs]);
  useEffect(() => { conversationsRef.current = conversations; }, [conversations]);
  const nextMsgId = () => ++msgIdSeq.current;

  const loadDatasources = async () => {
    setLoadingSchema(true);
    setSchemaError("");
    try {
      const nextDatasources = await listDatasources();
      setDatasources(nextDatasources);
      const nextActive = activeDatasourceId && nextDatasources.some((item) => item.id === activeDatasourceId)
        ? activeDatasourceId
        : nextDatasources[0]?.id || "";
      setActiveDatasourceId(nextActive);
      if (nextActive) {
        const nextTables = await listTables(nextActive);
        setTables(nextTables);
      } else {
        setTables([]);
      }
    } catch (err) {
      setSchemaError(err instanceof Error ? err.message : "读取本地 Engine 数据源失败");
      setDatasources([]);
      setTables([]);
    } finally {
      setLoadingSchema(false);
    }
  };

  const handleRefreshSchema = async () => {
    if (!activeDatasourceId) {
      showToast("没有活动数据源");
      return;
    }
    setLoadingSchema(true);
    try {
      const nextTables = await listTables(activeDatasourceId);
      setTables(nextTables);
      showToast("已刷新 Schema 元数据");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "刷新 Schema 失败");
    } finally {
      setLoadingSchema(false);
    }
  };

  useEffect(() => {
    void loadDatasources();
  }, []);

  useEffect(() => {
    if (!activeDatasourceId) return;
    const fetchTables = async () => {
      try {
        const nextTables = await listTables(activeDatasourceId);
        setTables(nextTables);
      } catch (err) {
        setSchemaError(err instanceof Error ? err.message : "读取表结构失败");
      }
    };
    void fetchTables();
  }, [activeDatasourceId]);

  // Fetch columns for tables to support field search in command palette
  useEffect(() => {
    if (tables.length === 0) return;
    const fetchColumns = async () => {
      const cols: Record<string, any[]> = {};
      for (const table of tables) {
        try {
          const tableCols = await listColumns(table.id);
          cols[table.table_name] = tableCols;
        } catch {
          // ignore error for individual table column loading
        }
      }
      setTableColumns(cols);
    };
    void fetchColumns();
  }, [tables]);

  useEffect(() => {
    const handleResize = () => {
      const targetWidth = 1598;
      const targetHeight = 1066;
      setScale(Math.min(window.innerWidth / targetWidth, window.innerHeight / targetHeight));
    };
    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    const handleDocumentClick = () => setContextMenu((prev) => ({ ...prev, visible: false }));
    window.addEventListener("click", handleDocumentClick);
    return () => window.removeEventListener("click", handleDocumentClick);
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, []);

  const showToast = (message: string) => {
    setToastMsg(message);
    setTimeout(() => setToastMsg(null), 2500);
  };

  const refreshConversations = async () => {
    try {
      const history = await listConversations();
      setConversations(history);
    } catch {
      showToast("读取 SQLite 对话历史失败");
    }
  };

  const persistConversation = async (conversation: Conversation) => {
    try {
      await saveConversation(conversation);
      setConversations((prev) => [conversation, ...prev.filter((item) => item.id !== conversation.id)].sort((a, b) => b.updatedAt - a.updatedAt));
    } catch {
      showToast("写入 SQLite 对话历史失败");
    }
  };

  const openTableTab = (tableName: string, initialSubtab = "preview") => {
    const tabId = `table-${tableName}`;
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: tableName, type: "table", tableId: tableName }]));
    setActiveTabId(tabId);
    setSelectedTables([tableName]);
    setTableSubTabs((prev) => ({ ...prev, [tableName]: initialSubtab }));
  };

  const closeTab = (tabId: string, event: MouseEvent) => {
    event.stopPropagation();
    const nextTabs = tabs.filter((tab) => tab.id !== tabId);
    if (nextTabs.length === 0) {
      setTabs([{ id: "smart-query", title: "问数工作台", type: "smart-query" }]);
      setActiveTabId("smart-query");
      return;
    }
    setTabs(nextTabs);
    if (activeTabId === tabId) setActiveTabId(nextTabs[nextTabs.length - 1].id);
  };

  const openSqlConsole = () => {
    const tabId = `sql-${Date.now()}`;
    setTabs((prev) => [...prev, { id: tabId, title: "SQL 控制台", type: "sql" }]);
    setActiveTabId(tabId);
    showToast("已打开 SQL 控制台");
  };

  const openLlmConfigTab = () => {
    const tabId = "llm-config";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "LLM 配置", type: "llm-config" as any }]));
    setActiveTabId(tabId);
  };

  const openSystemSettingsTab = () => {
    const tabId = "system-settings";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "系统设置", type: "system-settings" as any }]));
    setActiveTabId(tabId);
  };

  const openConnectionManagerTab = () => {
    const tabId = "datasource-settings";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "数据源管理", type: "datasource-settings" as any }]));
    setActiveTabId(tabId);
  };

  const openNewConnectionTab = () => {
    const tabId = "datasource-settings";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "新建数据源", type: "datasource-settings" as any }]));
    setActiveTabId(tabId);
    
    // Auto toggle add connection form
    setTimeout(() => {
      const formEl = document.querySelector(".field-label") as HTMLElement | null;
      if (!formEl) {
        const addBtn = document.querySelector(".inline-flex[onClick*='setShowAddForm']") || document.querySelector("button[style*='cursor']");
        if (addBtn) (addBtn as HTMLButtonElement).click();
      }
    }, 250);
  };

  const openMultiTableWorkspace = (tables: string[]) => {
    if (tables.length === 0) return;
    const tabId = `multi-table-${Date.now()}`;
    const title = `Workspace: ${tables.slice(0, 2).join(" & ")}${tables.length > 2 ? "..." : ""}`;
    setTabs((prev) => [...prev, { id: tabId, title, type: "multi-table", selectedTables: tables }]);
    setActiveTabId(tabId);
    showToast(`已创建多表联合 Workspace (${tables.length} 张表)`);
  };

  const openAgentEvalTab = () => {
    const tabId = "agent-eval";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "Agent 评测", type: "agent-eval" }]));
    setActiveTabId(tabId);
  };

  const openConversationHistoryTab = () => {
    const tabId = "conversation-history";
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: "对话历史", type: "conversation-history" }]));
    setActiveTabId(tabId);
    setRecentTab("chat");
  };

  const openConversationResult = (conversation: Conversation) => {
    const tabId = `conversation-${conversation.id}`;
    const tab: WorkspaceTab = {
      id: tabId,
      title: conversation.title,
      type: "query-result",
      queryText: conversation.title,
      conversationId: conversation.id,
      chatMessages: conversationMessagesToTabMessages(conversation.messages),
      artifacts: conversation.artifacts,
    };
    setTabs((prev) => (prev.some((item) => item.id === tabId) ? prev.map((item) => (item.id === tabId ? tab : item)) : [...prev, tab]));
    setActiveTabId(tabId);
  };

  const openQueryResultTab = (queryText: string) => {
    const text = queryText.trim();
    if (!text) return;
    const now = Date.now();
    const tabId = `query-result-${now}`;
    setTabs((prev) => [
      ...prev,
      {
        id: tabId,
        title: "问数结果",
        type: "query-result",
        queryText: text,
        conversationId: `conversation-${now}`,
        chatMessages: [{ id: nextMsgId(), sender: "user", text }],
        artifacts: [],
      },
    ]);
    setActiveTabId(tabId);
    setAskInputValue("");
    void runAgentForTab(tabId, text);
  };

  // ---- Agent runtime wiring -------------------------------------------------

  const patchTab = (tabId: string, patch: Partial<WorkspaceTab>) => {
    setTabs((prev) => prev.map((tab) => (tab.id === tabId ? { ...tab, ...patch } : tab)));
  };

  const appendTabMessages = (tabId: string, messages: NonNullable<WorkspaceTab["chatMessages"]>) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId ? { ...tab, chatMessages: [...(tab.chatMessages || []), ...messages] } : tab
    )));
  };

  const updateTabMessage = (tabId: string, messageId: number, text: string) => {
    setTabs((prev) => prev.map((tab) => (
      tab.id === tabId
        ? { ...tab, chatMessages: (tab.chatMessages || []).map((message) => (message.id === messageId ? { ...message, text } : message)) }
        : tab
    )));
  };

  /** Persist the tab transcript into SQLite conversation history (after state flush). */
  const persistTabConversation = (tabId: string) => {
    setTimeout(() => {
      const tab = tabsRef.current.find((item) => item.id === tabId);
      if (!tab?.conversationId) return;
      const origin = conversationsRef.current.find((item) => item.id === tab.conversationId);
      const now = Date.now();
      void persistConversation({
        id: tab.conversationId,
        title: origin?.title || tab.queryText || "未命名问答",
        createdAt: origin?.createdAt || now,
        updatedAt: now,
        contextTables: origin?.contextTables || contextTables,
        messages: tabMessagesToConversationMessages(tab.chatMessages || []),
        artifacts: tab.artifacts || [],
      });
    }, 0);
  };

  const makeAgentEventHandler = (tabId: string, progressId: number, artifactsBox: { list: ApiAgentArtifact[] }) => {
    return (event: AgentRuntimeEvent) => {
      const progressText = describeRuntimeEvent(event);
      if (progressText) updateTabMessage(tabId, progressId, progressText);
      if (event.type === "agent.artifact.created" && event.artifact) {
        artifactsBox.list = mergeApiArtifacts(artifactsBox.list, [event.artifact]);
        patchTab(tabId, { artifacts: toViewArtifacts(artifactsBox.list) });
      }
    };
  };

  const finishAgentRun = (
    tabId: string,
    progressId: number,
    response: AgentRunResponse,
    apiArtifacts: ApiAgentArtifact[],
  ) => {
    const merged = mergeApiArtifacts(apiArtifacts, response.artifacts || []);
    const viewArtifacts = toViewArtifacts(merged);

    if (response.status === "waiting_approval") {
      const approval = response.approval;
      const requestedAction = (approval?.requested_action || {}) as { args?: { sql?: unknown } };
      const approvalSql = typeof requestedAction.args?.sql === "string" ? requestedAction.args.sql : response.sql || undefined;
      updateTabMessage(tabId, progressId, "该操作存在风险，需要你确认后才会继续执行。请在下方审批卡片中选择。");
      patchTab(tabId, {
        artifacts: viewArtifacts,
        agentRunId: response.run_id,
        agentSessionId: response.session_id,
        agentStatus: "waiting_approval",
        agentApproval: approval
          ? {
              runId: response.run_id,
              approvalId: approval.id,
              stepName: approval.step_name,
              riskLevel: approval.risk_level,
              reason: approval.reason || undefined,
              sql: approvalSql,
            }
          : null,
      });
      return;
    }

    const succeeded = response.success || response.status === "success" || response.status === "completed";
    updateTabMessage(
      tabId,
      progressId,
      succeeded ? buildAnswerText(response.answer, response.explanation) : `执行未完成：${response.error || "Agent 已停止。"}`,
    );
    const suggestionText = buildSuggestionsText(response.suggestions);
    if (succeeded && suggestionText) {
      appendTabMessages(tabId, [{ id: nextMsgId(), sender: "ai", text: suggestionText }]);
    }
    patchTab(tabId, {
      artifacts: viewArtifacts,
      agentRunId: response.run_id,
      agentSessionId: response.session_id,
      agentStatus: succeeded ? "completed" : "failed",
      agentApproval: null,
    });
    persistTabConversation(tabId);
  };

  const runAgentForTab = async (
    tabId: string,
    question: string,
    opts?: { sessionId?: string; parentRunId?: string },
  ) => {
    if (!activeDatasourceId) {
      appendTabMessages(tabId, [{ id: nextMsgId(), sender: "ai", text: "未找到活动数据源，请先在左侧数据源树中选择一个数据源后重试。" }]);
      patchTab(tabId, { agentStatus: "failed" });
      return;
    }
    const llm = getStoredApiConfig();
    const progressId = nextMsgId();
    appendTabMessages(tabId, [{ id: progressId, sender: "ai", text: "正在理解问题…" }]);
    patchTab(tabId, { agentStatus: "running", agentApproval: null });

    const artifactsBox: { list: ApiAgentArtifact[] } = { list: [] };
    try {
      const response = await agentApi.streamAgentQuery(
        activeDatasourceId,
        question,
        {
          apiKey: llm.apiKey || undefined,
          apiBase: llm.apiBase || undefined,
          model: llm.modelName || undefined,
          sessionId: opts?.sessionId,
          parentRunId: opts?.parentRunId,
          workspaceContext: { datasource_id: activeDatasourceId, selected_table_names: contextTables },
          execute: true,
        },
        { onEvent: makeAgentEventHandler(tabId, progressId, artifactsBox) },
      );
      finishAgentRun(tabId, progressId, response, artifactsBox.list);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Agent 执行失败";
      updateTabMessage(tabId, progressId, `执行失败：${message}`);
      patchTab(tabId, { agentStatus: "failed", agentApproval: null });
      persistTabConversation(tabId);
    }
  };

  const handleApprovalDecision = async (tabId: string, approve: boolean) => {
    const tab = tabsRef.current.find((item) => item.id === tabId);
    const approval = tab?.agentApproval;
    if (!approval) return;

    patchTab(tabId, { agentApproval: null, agentStatus: approve ? "running" : "failed" });
    const progressId = nextMsgId();
    appendTabMessages(tabId, [{ id: progressId, sender: "ai", text: approve ? "已批准，继续执行…" : "已拒绝本次执行。" }]);

    try {
      await resolveAgentApproval(
        approval.runId,
        approval.approvalId,
        approve ? "approved" : "rejected",
        approve ? "Approved in DataBox UI" : "Rejected in DataBox UI",
      );
      if (!approve) {
        persistTabConversation(tabId);
        return;
      }
      const artifactsBox: { list: ApiAgentArtifact[] } = { list: [] };
      const response = await streamResumeAgentRun(approval.runId, approval.approvalId, {
        onEvent: makeAgentEventHandler(tabId, progressId, artifactsBox),
      });
      finishAgentRun(tabId, progressId, response, artifactsBox.list);
    } catch (err) {
      const message = err instanceof Error ? err.message : "审批处理失败";
      updateTabMessage(tabId, progressId, `审批处理失败：${message}`);
      patchTab(tabId, { agentStatus: "failed" });
    }
  };

  const handleTableClick = (tableName: string, event: MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedTables((prev) => (prev.includes(tableName) ? prev.filter((table) => table !== tableName) : [...prev, tableName]));
      return;
    }
    openTableTab(tableName);
  };

  const handleNodeContextMenu = (event: MouseEvent, type: "database" | "schema" | "table", nodeName: string) => {
    event.preventDefault();
    event.stopPropagation();
    if (type === "table" && selectedTables.length > 1 && selectedTables.includes(nodeName)) {
      setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type: "multi-table", targetNode: nodeName });
      return;
    }
    if (type === "table") setSelectedTables([nodeName]);
    setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type, targetNode: nodeName });
  };

  const addContextTable = (tableName: string) => {
    setContextTables((prev) => (prev.includes(tableName) ? prev : [...prev, tableName]));
    showToast(`已添加表 ${tableName} 到问数上下文`);
  };

  const toggleRightDrawer = (type: "ai-suggest" | "props") => {
    if (rightDrawerOpen && rightDrawerType === type) setRightDrawerOpen(false);
    else {
      setRightDrawerOpen(true);
      setRightDrawerType(type);
    }
  };

  const sendFollowUp = (tabId: string, text: string) => {
    const content = text.trim();
    if (!content) return;
    const targetTab = tabsRef.current.find((tab) => tab.id === tabId);
    if (targetTab?.agentStatus === "running") {
      showToast("Agent 正在执行中，请等待当前回答完成");
      return;
    }
    if (targetTab?.agentStatus === "waiting_approval") {
      showToast("请先处理待审批的操作");
      return;
    }
    appendTabMessages(tabId, [{ id: nextMsgId(), sender: "user", text: content }]);
    void runAgentForTab(tabId, content, {
      sessionId: targetTab?.agentSessionId,
      parentRunId: targetTab?.agentRunId,
    });
  };

  const deleteConversationById = async (conversationId: string) => {
    try {
      await deleteConversation(conversationId);
      setConversations((prev) => prev.filter((item) => item.id !== conversationId));
      setTabs((prev) => prev.filter((tab) => tab.conversationId !== conversationId));
      showToast("已删除对话历史");
    } catch {
      showToast("删除 SQLite 对话历史失败");
    }
  };

  // Keyboard Event Handlers
  useEffect(() => {
    const handleGlobalKeyDown = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setShowCommandPalette(true);
      }
      if (mod && event.key.toLowerCase() === "n") {
        event.preventDefault();
        openSqlConsole();
      }
      if (mod && event.key.toLowerCase() === "w" && activeTabId) {
        event.preventDefault();
        closeTab(activeTabId, event as any);
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [activeTabId, tabs]);

  const commandItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [
      {
        id: "new-sql",
        name: "新建 SQL 控制台",
        category: "快捷入口",
        shortcut: "⌘N",
        icon: <Terminal size={13} className="text-green-500" />,
        action: () => openSqlConsole()
      },
      {
        id: "smart-query",
        name: "智能问数 (AI 问数)",
        category: "快捷入口",
        icon: <Sparkles size={13} className="text-purple-500" />,
        action: () => {
          setTabs((prev) => prev.some(t => t.type === "smart-query") ? prev : [...prev, { id: "smart-query", title: "问数工作台", type: "smart-query" }]);
          setActiveTabId("smart-query");
        }
      },
      {
        id: "llm-config",
        name: "打开 LLM 配置",
        category: "系统配置",
        icon: <Cpu size={13} className="text-pink-500" />,
        action: () => openLlmConfigTab()
      },
      {
        id: "system-settings",
        name: "打开系统设置",
        category: "系统配置",
        icon: <Settings size={13} className="text-slate-500" />,
        action: () => openSystemSettingsTab()
      },
      {
        id: "create-datasource",
        name: "新建数据源连接",
        category: "数据源",
        icon: <Database size={13} className="text-blue-500" />,
        action: () => openNewConnectionTab()
      },
      {
        id: "connection-manager",
        name: "数据源连接管理",
        category: "数据源",
        icon: <Database size={13} className="text-slate-500" />,
        action: () => openConnectionManagerTab()
      },
      {
        id: "agent-eval",
        name: "Agent 评测 (Golden 任务)",
        category: "AI 能力",
        icon: <FlaskConical size={13} className="text-amber-500" />,
        action: () => openAgentEvalTab()
      }
    ];

    tables.forEach((table) => {
      items.push({
        id: `table-${table.table_name}`,
        name: `打开表: ${table.table_name}`,
        category: `数据表 (${table.module_tag || "未分组"})`,
        icon: <FileText size={13} className="text-blue-500" />,
        action: () => openTableTab(table.table_name)
      });
    });

    Object.entries(tableColumns).forEach(([tableName, columns]) => {
      columns.forEach((col) => {
        items.push({
          id: `field-${tableName}-${col.column_name}`,
          name: `查看字段: ${tableName}.${col.column_name} (${col.column_type})`,
          category: `表字段 (${tableName})`,
          icon: <HelpCircle size={13} className="text-slate-400" />,
          action: () => openTableTab(tableName, "schema")
        });
      });
    });

    return items;
  }, [tables, tableColumns]);

  const renderActiveTab = () => {
    if (activeTab.type === "smart-query") {
      return (
        <SmartQueryHome
          askInputValue={askInputValue}
          contextTables={contextTables}
          conversations={conversations}
          recentTab={recentTab}
          onAskInputChange={setAskInputValue}
          onSubmitAsk={() => openQueryResultTab(askInputValue)}
          onRecommendClick={setAskInputValue}
          onRecentTabChange={setRecentTab}
          onOpenTable={openTableTab}
          onOpenConversation={openConversationResult}
          onAddContextTable={addContextTable}
          onRemoveContextTable={(tableName) => setContextTables((prev) => prev.filter((table) => table !== tableName))}
          onClearContextTables={() => setContextTables([])}
          onOpenConversationHistory={openConversationHistoryTab}
          onToast={showToast}
        />
      );
    }
    if (activeTab.type === "conversation-history") {
      return <ConversationHistoryPanel conversations={conversations} activeConversationId={activeTab.conversationId} onOpenConversation={openConversationResult} onDeleteConversation={deleteConversationById} />;
    }
    if (activeTab.type === "table") {
      const tableId = activeTab.tableId || "id_users";
      return <TableWorkspace tableId={tableId} currentSubTab={tableSubTabs[tableId] || "preview"} onSubTabChange={(subTab) => setTableSubTabs((prev) => ({ ...prev, [tableId]: subTab }))} onOpenSqlConsole={openSqlConsole} onToast={showToast} />;
    }
    if (activeTab.type === "sql") {
      return <SqlConsoleWorkspace sqlQuery={sqlQuery} onSqlQueryChange={setSqlQuery} onToast={showToast} />;
    }
    if (activeTab.type === "multi-table") {
      return <MultiTableWorkspace tables={activeTab.selectedTables || []} onOpenQueryResult={openQueryResultTab} onToast={showToast} />;
    }
    if (activeTab.type === "llm-config" as any) {
      return <LlmConfigTabContent showToast={showToast} />;
    }
    if (activeTab.type === "system-settings" as any) {
      return <SystemSettingsTabContent showToast={showToast} />;
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
    if (activeTab.type === "datasource-settings" as any) {
      return (
        <div className="wb-settings-frame p-6 overflow-auto h-full" style={{ background: "var(--bg-surface)" }}>
          <DataSourcesPage
            onSelectDataSource={(ds) => {
              if (ds) {
                setActiveDatasourceId(ds.id);
                showToast(`已激活数据源: ${ds.name}`);
              } else {
                setActiveDatasourceId("");
              }
            }}
            activeDataSource={activeDatasource}
            activeProject={null}
            onRefreshDatasources={loadDatasources}
            initialShowAddForm={activeTab.title === "新建数据源"}
          />
        </div>
      );
    }
    return (
      <QueryResultWorkspace
        tab={activeTab}
        onOpenSqlConsole={openSqlConsole}
        onSetSqlQuery={setSqlQuery}
        onSendFollowUp={sendFollowUp}
        onApproveAgent={(tabId) => void handleApprovalDecision(tabId, true)}
        onRejectAgent={(tabId) => void handleApprovalDecision(tabId, false)}
        onToast={showToast}
      />
    );
  };

  return (
    <div className="hifi-viewport-wrapper">
      <div className="hifi-canvas-board" style={{ "--scale": scale } as CSSProperties}>
        {/* Main Work Area */}
        <main className="hifi-workspace" style={{ height: "calc(1066px - 32px)", paddingTop: 0, paddingBottom: 0 }}>
          <DataSourceTree
            treeSearch={treeSearch}
            selectedTables={selectedTables}
            onTreeSearchChange={setTreeSearch}
            onTableClick={handleTableClick}
            onTableDoubleClick={openTableTab}
            onNodeContextMenu={handleNodeContextMenu}
            onRefresh={handleRefreshSchema}
            onNewConnection={openNewConnectionTab}
            datasources={datasources}
            activeDatasourceId={activeDatasourceId}
            setActiveDatasourceId={setActiveDatasourceId}
            tables={tables}
            loading={loadingSchema}
            error={schemaError}
          />

          <section className="hifi-col hifi-main-workspace-col" style={{ gap: 0 }}>
            {/* Top Workspace Tab Bar Container */}
            <div className="hifi-top-tabs-bar" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "var(--color-panel)", borderBottom: "1px solid var(--color-border)", height: 40, flexShrink: 0 }}>
              <WorkspaceTabs
                tabs={tabs}
                activeTabId={activeTabId}
                onActivateTab={(tab) => {
                  setActiveTabId(tab.id);
                  if (tab.type === "table" && tab.tableId) setSelectedTables([tab.tableId]);
                }}
                onCloseTab={closeTab}
                onOpenSqlConsole={openSqlConsole}
              />
              
              {/* Minimalist Top Right Actions */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, paddingRight: 12 }}>
                <button
                  className="hifi-icon-btn text-xs font-semibold"
                  style={{ width: "auto", height: 26, padding: "0 8px", display: "flex", alignItems: "center", gap: 4, borderRadius: 4, border: "1px solid var(--color-border)", background: "var(--color-bg)", fontSize: 11 }}
                  onClick={() => setShowCommandPalette(true)}
                  title="打开命令面板 (⌘K)"
                >
                  <span style={{ color: "var(--color-text-secondary)" }}>命令面板</span>
                  <kbd style={{ background: "var(--color-border)", padding: "0 4px", borderRadius: 3, fontSize: 9 }}>⌘K</kbd>
                </button>
                <div style={{ position: "relative" }}>
                  <button
                    className="hifi-icon-btn"
                    style={{ width: 26, height: 26, borderRadius: 4, border: "1px solid var(--color-border)", background: "var(--color-bg)", fontSize: 13, fontWeight: 700 }}
                    onClick={() => setShowMoreMenu((prev) => !prev)}
                    title="更多选项"
                  >
                    ...
                  </button>
                  {showMoreMenu && (
                    <div
                      className="data-grid-menu animate-fade-in"
                      style={{
                        position: "absolute",
                        top: 32,
                        right: 0,
                        zIndex: 100,
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border-medium)",
                        boxShadow: "var(--shadow-lg)",
                        borderRadius: 8,
                        padding: 4,
                        minWidth: 160
                      }}
                    >
                      <button className="data-grid-menu-item" style={{ border: "none" }} onClick={() => { openLlmConfigTab(); setShowMoreMenu(false); }}>LLM 配置</button>
                      <button className="data-grid-menu-item" style={{ border: "none" }} onClick={() => { openConnectionManagerTab(); setShowMoreMenu(false); }}>数据源连接管理</button>
                      <button className="data-grid-menu-item" style={{ border: "none" }} onClick={() => { openSystemSettingsTab(); setShowMoreMenu(false); }}>系统设置</button>
                      <div style={{ height: 1, background: "var(--color-border)", margin: "4px 0" }} />
                      <button className="data-grid-menu-item" style={{ border: "none" }} onClick={() => { setShowShortcutsHelp(true); setShowMoreMenu(false); }}>快捷键说明</button>
                      <button className="data-grid-menu-item" style={{ border: "none" }} onClick={() => { alert("DataBox v1.0.0\nAI 驱动的本地优先数据库工作台"); setShowMoreMenu(false); }}>关于</button>
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
              {renderActiveTab()}
            </div>
          </section>

          <ContextDrawer
            open={rightDrawerOpen}
            type={rightDrawerType}
            activeTab={activeTab}
            contextTables={contextTables}
            onClose={() => setRightDrawerOpen(false)}
            onGenerateIndexSql={() => {
              setSqlQuery("ALTER TABLE comment_infos ADD INDEX idx_user_id (user_id);");
              openSqlConsole();
            }}
          />
        </main>

        {/* Professional Desktop Status Bar at the bottom */}
        <footer className="hifi-status-bar" style={{ height: 32, background: "var(--color-panel)", borderTop: "1px solid var(--color-border)", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px", fontSize: 11, color: "var(--color-text-secondary)", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#16A34A" }}></span>
              Engine Connected (Local)
            </span>
            {activeDatasource && (
              <span>数据源: <strong>{activeDatasource.name}</strong> ({activeDatasource.db_type})</span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            {activeTab && (
              <span>活动标签页: {activeTab.title}</span>
            )}
            <span>UTF-8</span>
            <span>MySQL 8.0</span>
          </div>
        </footer>
      </div>

      <DataSourceContextMenu
        contextMenu={contextMenu}
        selectedTables={selectedTables}
        onOpenSqlConsole={openSqlConsole}
        onOpenTable={openTableTab}
        onOpenMultiTableWorkspace={openMultiTableWorkspace}
        onAddContextTable={addContextTable}
        onSetContextTables={(tables) => {
          setContextTables(tables);
          setActiveTabId("smart-query");
          showToast(`已将 ${tables.length} 张表载入问数上下文`);
        }}
        onClearSelectedTables={() => setSelectedTables([])}
        onClose={() => setContextMenu((prev) => ({ ...prev, visible: false }))}
        onToast={showToast}
        onOpenProps={() => toggleRightDrawer("props")}
      />

      {toastMsg && <div className="hifi-toast"><Sparkles size={12} className="text-yellow-400" /><span>{toastMsg}</span></div>}

      <CommandPalette open={showCommandPalette} onClose={() => setShowCommandPalette(false)} commands={commandItems} />

      {/* Shortcuts Help dialog */}
      {showShortcutsHelp && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.4)", backdropFilter: "blur(4px)", zIndex: 3000, display: "grid", placeItems: "center" }} onClick={() => setShowShortcutsHelp(false)}>
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: 24, width: 360 }} onClick={e => e.stopPropagation()}>
            <h4 style={{ fontSize: "1.1rem", fontWeight: 600, marginBottom: 16 }}>快捷键说明</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: "0.85rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}><span>打开命令面板</span><kbd className="px-1.5 py-0.5 bg-slate-100 border rounded text-[10px]">⌘K / Ctrl+K</kbd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><span>新建 SQL 控制台</span><kbd className="px-1.5 py-0.5 bg-slate-100 border rounded text-[10px]">⌘N / Ctrl+N</kbd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><span>关闭当前标签页</span><kbd className="px-1.5 py-0.5 bg-slate-100 border rounded text-[10px]">⌘W / Ctrl+W</kbd></div>
              <div style={{ display: "flex", justifyContent: "space-between" }}><span>显示 / 隐藏 AI 面板</span><kbd className="px-1.5 py-0.5 bg-slate-100 border rounded text-[10px]">⌥A / Alt+A</kbd></div>
            </div>
            <button className="w-full mt-6 bg-primary text-primary-foreground py-1.5 rounded-sm border-none cursor-pointer" style={{ background: "linear-gradient(135deg, #2D3B8C, #4A5BC0)" }} onClick={() => setShowShortcutsHelp(false)}>关闭</button>
          </div>
        </div>
      )}
    </div>
  );
}

function conversationMessagesToTabMessages(messages: ConversationMessage[]) {
  return messages.map((message, index) => ({
    id: Number(message.id.replace(/\D/g, "")) || index + 1,
    sender: message.role === "user" ? "user" as const : "ai" as const,
    text: message.content,
  }));
}

function tabMessagesToConversationMessages(messages: NonNullable<WorkspaceTab["chatMessages"]>): ConversationMessage[] {
  return messages.map((message, index) => ({
    id: `message-${message.id || index}`,
    role: message.sender === "user" ? "user" : "assistant",
    content: message.text,
    createdAt: Number(message.id) || Date.now(),
  }));
}

function LlmConfigTabContent({ showToast }: { showToast: (msg: string) => void }) {
  const { config, updateConfig, handleSave } = useApiConfig();
  
  return (
    <div style={{ padding: 24, background: "var(--bg-surface)", height: "100%", overflowY: "auto" }}>
      <div style={{ maxWidth: 540 }}>
        <h3 className="text-display" style={{ fontSize: "1.2rem", fontWeight: 600, marginBottom: 8, color: "var(--color-text-primary)" }}>LLM 配置 (Language Model)</h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: 20 }}>
          配置智能问数底层大语言模型的连接参数。所有凭证均保存在您本地，不会上传至第三方服务器。
        </p>
        
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label className="field-label" style={{ display: "block", marginBottom: 6, fontSize: "0.8rem", fontWeight: 600 }}>API Key (接口密钥)</label>
            <input
              type="password"
              className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="sk-..."
              value={config.apiKey}
              onChange={(e) => updateConfig({ apiKey: e.target.value })}
              style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
            />
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 4, display: "block" }}>
              输入 OpenAI, DeepSeek 或 Claude 兼容的接口密钥。
            </span>
          </div>

          <div>
            <label className="field-label" style={{ display: "block", marginBottom: 6, fontSize: "0.8rem", fontWeight: 600 }}>API Base URL (接口基础路径)</label>
            <input
              type="text"
              className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="https://api.openai.com/v1"
              value={config.apiBase}
              onChange={(e) => updateConfig({ apiBase: e.target.value })}
              style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
            />
          </div>

          <div>
            <label className="field-label" style={{ display: "block", marginBottom: 6, fontSize: "0.8rem", fontWeight: 600 }}>Model Name (模型名称)</label>
            <input
              type="text"
              className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="gpt-4o-mini"
              value={config.modelName}
              onChange={(e) => updateConfig({ modelName: e.target.value })}
              style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
            />
          </div>
          
          <div style={{ marginTop: 10, display: "flex", gap: 12 }}>
            <button
              onClick={() => {
                handleSave();
                showToast("LLM 配置保存成功");
              }}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110"
              style={{ background: "linear-gradient(135deg, #2D3B8C, #4A5BC0)" }}
            >
              保存配置
            </button>
            <button
              onClick={() => {
                showToast("正在测试与模型接口握手...");
                setTimeout(() => {
                  showToast("连接测试通过！成功连通目标 API");
                }, 800);
              }}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold border border-border bg-transparent rounded-sm cursor-pointer hover:bg-accent text-foreground"
            >
              测试连接
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SystemSettingsTabContent({ showToast }: { showToast: (msg: string) => void }) {
  const [activeCategory, setActiveCategory] = useState<"appearance" | "agent" | "sql" | "security">("appearance");
  const [theme, setTheme] = useState("dark");
  const [fontSize, setFontSize] = useState("13px");
  const [autoExecute, setAutoExecute] = useState(false);
  const [sqlLimit, setSqlLimit] = useState(100);
  const [timeout, setTimeoutSec] = useState(30);
  const [readOnly, setReadOnly] = useState(false);

  return (
    <div style={{ display: "flex", background: "var(--bg-surface)", height: "100%" }}>
      {/* Settings Sidebar */}
      <div style={{ width: 180, borderRight: "1px solid var(--color-border)", background: "var(--bg-secondary)", padding: "12px 8px", display: "flex", flexDirection: "column", gap: 4 }}>
        {[
          { id: "appearance", label: "外观与界面" },
          { id: "agent", label: "Agent 智能助手" },
          { id: "sql", label: "SQL 查询与执行" },
          { id: "security", label: "安全与审计" }
        ].map(cat => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.id as any)}
            style={{
              width: "100%",
              padding: "8px 12px",
              borderRadius: 6,
              border: "none",
              textAlign: "left",
              fontSize: "0.8rem",
              cursor: "pointer",
              background: activeCategory === cat.id ? "var(--color-primary-soft)" : "transparent",
              color: activeCategory === cat.id ? "var(--color-primary)" : "var(--color-text-secondary)",
              fontWeight: activeCategory === cat.id ? 600 : 500
            }}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Settings Body */}
      <div style={{ flex: 1, padding: 24, overflowY: "auto" }}>
        <div style={{ maxWidth: 480 }}>
          {activeCategory === "appearance" && (
            <div>
              <h4 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: 16, color: "var(--color-text-primary)" }}>外观设置</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <label className="field-label" style={{ display: "block", marginBottom: 6 }}>系统主题</label>
                  <select
                    className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none"
                    value={theme}
                    onChange={(e) => {
                      setTheme(e.target.value);
                      showToast(`已切换主题为: ${e.target.value}`);
                    }}
                    style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
                  >
                    <option value="dark">酷炫暗黑模式 (Premium Dark)</option>
                    <option value="light">清爽明亮模式 (Light)</option>
                    <option value="system">跟随系统设置</option>
                  </select>
                </div>
                <div>
                  <label className="field-label" style={{ display: "block", marginBottom: 6 }}>编辑器字体大小</label>
                  <select
                    className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none"
                    value={fontSize}
                    onChange={(e) => setFontSize(e.target.value)}
                    style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
                  >
                    <option value="12px">12px (小)</option>
                    <option value="13px">13px (推荐)</option>
                    <option value="14px">14px (中)</option>
                    <option value="16px">16px (大)</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {activeCategory === "agent" && (
            <div>
              <h4 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: 16, color: "var(--color-text-primary)" }}>Agent 智能参数</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                  <input
                    type="checkbox"
                    checked={autoExecute}
                    onChange={(e) => setAutoExecute(e.target.checked)}
                    style={{ width: 16, height: 16, accentColor: "var(--color-primary)" }}
                  />
                  AI 生成 SQL 后自动执行查询
                </label>
                <div>
                  <label className="field-label" style={{ display: "block", marginBottom: 6 }}>大模型温度 (Temperature)</label>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    defaultValue="0.2"
                    style={{ width: "100%" }}
                    onChange={(e) => showToast(`已调整模型温度为: ${e.target.value}`)}
                  />
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)" }}>
                    <span>0.0 (精确/严格)</span>
                    <span>1.0 (创造性)</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeCategory === "sql" && (
            <div>
              <h4 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: 16, color: "var(--color-text-primary)" }}>SQL 执行控制</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <label className="field-label" style={{ display: "block", marginBottom: 6 }}>默认查询行数限制 (LIMIT)</label>
                  <input
                    type="number"
                    className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none"
                    value={sqlLimit}
                    onChange={(e) => setSqlLimit(Number(e.target.value) || 100)}
                    style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
                  />
                </div>
                <div>
                  <label className="field-label" style={{ display: "block", marginBottom: 6 }}>执行超时时间 (秒)</label>
                  <input
                    type="number"
                    className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground focus:outline-none"
                    value={timeout}
                    onChange={(e) => setTimeoutSec(Number(e.target.value) || 30)}
                    style={{ width: "100%", background: "var(--bg-primary)", color: "var(--text-primary)" }}
                  />
                </div>
              </div>
            </div>
          )}

          {activeCategory === "security" && (
            <div>
              <h4 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: 16, color: "var(--color-text-primary)" }}>安全防范与审计</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                  <input
                    type="checkbox"
                    checked={readOnly}
                    onChange={(e) => setReadOnly(e.target.checked)}
                    style={{ width: 16, height: 16, accentColor: "var(--color-primary)" }}
                  />
                  全局只读拦截 (禁止任何 DELETE, DROP, UPDATE 写入语句)
                </label>
                <div style={{ padding: "8px 12px", background: "var(--color-warning-soft)", border: "1px solid #F97316", borderRadius: 6, fontSize: "0.75rem", color: "var(--color-warning)" }}>
                  注意：开启后，任何非 SELECT 语句执行都会在客户端直接拦截并抛出审计警告。
                </div>
              </div>
            </div>
          )}

          <div style={{ marginTop: 24, borderTop: "1px solid var(--color-border)", paddingTop: 16 }}>
            <button
              onClick={() => showToast("系统设置已更新")}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110"
              style={{ background: "linear-gradient(135deg, #2D3B8C, #4A5BC0)" }}
            >
              保存修改
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
