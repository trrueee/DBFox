import { useState, useMemo, useEffect, useRef } from "react";
import { api } from "../lib/api";
import type { DataSource, GuardrailCheckResult, QueryResult } from "../lib/api";

export type QueryStatus = "idle" | "running" | "success" | "error" | "timeout" | "cancelled";

export type QueryTabState = {
  id: string;
  title: string;
  sql: string;
  savedSql: string;
  queryResult: QueryResult | null;
  queryError: string | null;
  guardrail: GuardrailCheckResult | null;
  schemaValidationWarnings?: string[];
  executionId?: string;
  status: QueryStatus;
};

const defaultSql = "SELECT * FROM your_table LIMIT 100;";

function createQueryTab(index: number): QueryTabState {
  return {
    id: `qt-${index}-${Date.now()}`,
    title: `Query ${index}`,
    sql: defaultSql,
    savedSql: defaultSql,
    queryResult: null,
    queryError: null,
    guardrail: null,
    schemaValidationWarnings: [],
    status: "idle",
  };
}

export const useQueryExecution = (datasource: DataSource, onExecuteSuccess?: () => void) => {
  const [tabs, setTabs] = useState<QueryTabState[]>([]);
  const [activeEditorTabId, setActiveEditorTabId] = useState("");
  const [validating, setValidating] = useState(false);
  const [renamingTabId, setRenamingTabId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  // Keep track of active AbortControllers mapped by tab ID so that cancellation is per-tab!
  const abortControllersRef = useRef<Record<string, AbortController>>({});

  // Initialize tabs when datasource ID changes
  useEffect(() => {
    const initialTab = createQueryTab(1);
    setTabs([initialTab]);
    setActiveEditorTabId(initialTab.id);
    setRenamingTabId(null);
    setRenameDraft("");

    // Cleanup any pending controllers on datasource swap
    Object.values(abortControllersRef.current).forEach((controller) => controller.abort());
    abortControllersRef.current = {};
  }, [datasource.id]);

  const activeEditorTab = useMemo(
    () => tabs.find((t) => t.id === activeEditorTabId) ?? tabs[0] ?? null,
    [activeEditorTabId, tabs],
  );

  const updateTabById = (tabId: string, updater: (tab: QueryTabState) => Partial<QueryTabState>) => {
    setTabs((currentTabs) =>
      currentTabs.map((t) => (t.id === tabId ? { ...t, ...updater(t) } : t))
    );
  };

  const updateActiveTab = (updater: (tab: QueryTabState) => Partial<QueryTabState>) => {
    if (!activeEditorTab) return;
    updateTabById(activeEditorTab.id, updater);
  };

  const requestServerCancel = (executionId?: string) => {
    if (!executionId) return;
    void api.cancelQuery(executionId).catch((error) => {
      console.error("Failed to cancel server-side query:", error);
    });
  };

  const handleAddTab = () => {
    const next = createQueryTab(tabs.length + 1);
    setTabs((c) => [...c, next]);
    setActiveEditorTabId(next.id);
    setRenamingTabId(null);
  };

  const handleCloseTab = (id: string) => {
    if (tabs.length === 1) return;
    const tab = tabs.find((t) => t.id === id);
    if (!tab) return;
    const isDirty = tab.sql !== tab.savedSql;
    if (isDirty && !window.confirm(`"${tab.title}" 还有未执行的修改，确认关闭吗？`)) return;

    // Abort if it's currently executing
    if (abortControllersRef.current[id]) {
      requestServerCancel(tab.executionId);
      abortControllersRef.current[id].abort();
      delete abortControllersRef.current[id];
    }

    const index = tabs.findIndex((t) => t.id === id);
    const nextTabs = tabs.filter((t) => t.id !== id);
    setTabs(nextTabs);
    if (activeEditorTabId === id) {
      setActiveEditorTabId(nextTabs[Math.max(0, index - 1)]?.id ?? nextTabs[0].id);
    }
    if (renamingTabId === id) {
      setRenamingTabId(null);
      setRenameDraft("");
    }
  };

  const startRenaming = (tab: QueryTabState) => {
    setRenamingTabId(tab.id);
    setRenameDraft(tab.title);
  };

  const commitRename = () => {
    if (!renamingTabId) return;
    const nextTitle = renameDraft.trim();
    updateTabById(renamingTabId, (t) => ({ title: nextTitle || t.title }));
    setRenamingTabId(null);
    setRenameDraft("");
  };

  const handleValidateSql = async () => {
    if (!activeEditorTab?.sql.trim()) return;
    try {
      setValidating(true);
      const guardrail = await api.validateSql(activeEditorTab.sql);
      updateActiveTab(() => ({ guardrail, queryError: null }));
    } catch (error: any) {
      updateActiveTab(() => ({ queryError: error.message ?? "SQL 校验失败" }));
    } finally {
      setValidating(false);
    }
  };

  // Execute SQL with Timeout & Cancellation Abort signals
  const handleExecuteSql = async (timeoutMs: number = 30000) => {
    if (!activeEditorTab?.sql.trim()) return;
    const tabId = activeEditorTab.id;

    // Double confirmation for PROD environment
    if (datasource.env === "prod") {
      const confirmRun = window.confirm(
        `⚠️ 安全警告：您当前正在对【生产环境 (PROD)】执行 SQL 操作！\n\n` +
        `数据源名称: ${datasource.name}\n` +
        `目标数据库: ${datasource.database_name}\n\n` +
        `执行线上环境操作可能会影响线上业务性能或触发审计日志。请确保 SQL 语句符合规范。\n\n` +
        `您确认要继续执行吗？`
      );
      if (!confirmRun) return;
    }

    // Cancel existing query execution on this tab if already running
    if (abortControllersRef.current[tabId]) {
      requestServerCancel(activeEditorTab.executionId);
      abortControllersRef.current[tabId].abort();
    }

    const controller = new AbortController();
    abortControllersRef.current[tabId] = controller;

    const execId = `exec-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

    updateTabById(tabId, () => ({
      status: "running",
      executionId: execId,
      queryError: null,
      queryResult: null,
    }));

    // Client-side execution timeout protection
    const timeoutId = setTimeout(() => {
      if (abortControllersRef.current[tabId] === controller) {
        requestServerCancel(execId);
        controller.abort("timeout");
      }
    }, timeoutMs);

    try {
      // Step 1: Run through guardrails safety check
      const checked = await api.validateSql(activeEditorTab.sql, controller.signal);
      updateTabById(tabId, () => ({ guardrail: checked }));

      if (checked.result === "reject") {
        clearTimeout(timeoutId);
        updateTabById(tabId, () => ({
          status: "error",
          queryError: `Guardrail 拒绝: ${checked.message}`
        }));
        delete abortControllersRef.current[tabId];
        return;
      }

      // Step 2: Send query execute request
      const result = await api.executeSql(datasource.id, activeEditorTab.sql, undefined, execId, controller.signal);

      clearTimeout(timeoutId);
      updateTabById(tabId, () => ({
        status: "success",
        queryResult: result,
        queryError: null,
        savedSql: activeEditorTab.sql,
      }));

      if (onExecuteSuccess) {
        onExecuteSuccess();
      }
    } catch (error: any) {
      clearTimeout(timeoutId);
      const isAborted = controller.signal.aborted;
      // Fetch uses abort DOMException, check if custom timeout was passed
      const isTimeout = isAborted && controller.signal.reason === "timeout";

      updateTabById(tabId, () => {
        if (isTimeout || error.code === "SQL_QUERY_TIMEOUT") {
          return {
            status: "timeout",
            queryError: `查询执行超时 (时间限制: ${timeoutMs / 1000} 秒)`
          };
        } else if (isAborted || error.code === "SQL_QUERY_CANCELLED") {
          return {
            status: "cancelled",
            queryError: "查询已被用户手动取消。"
          };
        } else {
          return {
            status: "error",
            queryError: error.message ?? "SQL 执行发生错误"
          };
        }
      });
    } finally {
      if (abortControllersRef.current[tabId] === controller) {
        delete abortControllersRef.current[tabId];
      }
    }
  };

  // Manual cancellation
  const handleCancelQuery = (tabId: string) => {
    const controller = abortControllersRef.current[tabId];
    const tab = tabs.find((t) => t.id === tabId);
    if (controller) {
      requestServerCancel(tab?.executionId);
      controller.abort();
      delete abortControllersRef.current[tabId];
      updateTabById(tabId, () => ({
        status: "cancelled",
        queryError: "查询已被用户手动取消。"
      }));
    }
  };

  return {
    tabs,
    setTabs,
    activeEditorTabId,
    setActiveEditorTabId,
    activeEditorTab,
    validating,
    renamingTabId,
    renameDraft,
    setRenameDraft,
    handleAddTab,
    handleCloseTab,
    startRenaming,
    commitRename,
    updateActiveTab,
    handleValidateSql,
    handleExecuteSql,
    handleCancelQuery,
  };
};
