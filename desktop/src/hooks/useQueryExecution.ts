import { useState, useMemo, useEffect, useRef, useCallback } from "react";
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

export interface ConfirmRequest {
  title: string;
  message: string;
  variant: "danger" | "warning" | "info";
  confirmLabel?: string;
  cancelLabel?: string;
  resolve: (confirmed: boolean) => void;
}

const defaultSql = "";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function getErrorCode(error: unknown): string | undefined {
  return typeof error === "object" && error !== null && "code" in error
    ? String((error as { code?: unknown }).code)
    : undefined;
}

function createQueryTab(index: number, sql = defaultSql, title?: string): QueryTabState {
  return {
    id: `qt-${index}-${Date.now()}`,
    title: title || `Query ${index}`,
    sql,
    savedSql: sql,
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
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null);
  const nextTabIndexRef = useRef(1);

  const requestConfirm = useCallback(
    (title: string, message: string, variant: "danger" | "warning" | "info" = "info"): Promise<boolean> => {
      return new Promise<boolean>((resolve) => {
        setConfirmRequest({ title, message, variant, resolve });
      });
    },
    [],
  );

  const resolveConfirm = useCallback((confirmed: boolean) => {
    setConfirmRequest((prev) => {
      prev?.resolve(confirmed);
      return null;
    });
  }, []);
  // Keep track of active AbortControllers mapped by tab ID so that cancellation is per-tab!
  const abortControllersRef = useRef<Record<string, AbortController>>({});

  // Initialize tabs when datasource ID changes
  useEffect(() => {
    const initialTab = createQueryTab(1);
    nextTabIndexRef.current = 2;
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

  const updateTabById = useCallback((tabId: string, updater: (tab: QueryTabState) => Partial<QueryTabState>) => {
    setTabs((currentTabs) =>
      currentTabs.map((t) => (t.id === tabId ? { ...t, ...updater(t) } : t))
    );
  }, []);

  const updateActiveTab = useCallback((updater: (tab: QueryTabState) => Partial<QueryTabState>) => {
    if (!activeEditorTab) return;
    updateTabById(activeEditorTab.id, updater);
  }, [activeEditorTab, updateTabById]);

  const requestServerCancel = useCallback((executionId?: string) => {
    if (!executionId) return;
    void api.cancelQuery(executionId).catch((error) => {
      console.warn(
        "Server-side query cancellation may have failed (best-effort). "
        + "The query was aborted locally but may still be running on the database. "
        + `executionId=${executionId}`,
        error,
      );
    });
  }, []);

  const handleAddTab = useCallback((sql?: string, title?: string) => {
    const next = createQueryTab(nextTabIndexRef.current, sql || defaultSql, title);
    nextTabIndexRef.current += 1;
    setTabs((c) => [...c, next]);
    setActiveEditorTabId(next.id);
    setRenamingTabId(null);
  }, []);

  const openSqlDraft = useCallback((sql: string, title?: string) => {
    const trimmedSql = sql.trim();
    if (!trimmedSql) return;
    handleAddTab(trimmedSql, title);
  }, [handleAddTab]);

  const handleCloseTab = useCallback(async (id: string) => {
    if (tabs.length === 1) return;
    const tab = tabs.find((t) => t.id === id);
    if (!tab) return;
    const isDirty = tab.sql !== tab.savedSql;
    if (isDirty) {
      const confirmed = await requestConfirm(
        "关闭标签页",
        `"${tab.title}" 还有未执行的修改，确认关闭吗？`,
        "warning",
      );
      if (!confirmed) return;
    }

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
  }, [activeEditorTabId, renamingTabId, requestConfirm, requestServerCancel, tabs]);

  const startRenaming = useCallback((tab: QueryTabState) => {
    setRenamingTabId(tab.id);
    setRenameDraft(tab.title);
  }, []);

  const commitRename = useCallback(() => {
    if (!renamingTabId) return;
    const nextTitle = renameDraft.trim();
    updateTabById(renamingTabId, (t) => ({ title: nextTitle || t.title }));
    setRenamingTabId(null);
    setRenameDraft("");
  }, [renameDraft, renamingTabId, updateTabById]);

  const handleValidateSql = useCallback(async () => {
    if (!activeEditorTab?.sql.trim()) return;
    try {
      setValidating(true);
      const guardrail = await api.validateSql(activeEditorTab.sql, { datasourceId: datasource.id });
      updateActiveTab(() => ({ guardrail, queryError: null }));
    } catch (error: unknown) {
      updateActiveTab(() => ({ queryError: getErrorMessage(error, "SQL 校验失败") }));
    } finally {
      setValidating(false);
    }
  }, [activeEditorTab, datasource.id, updateActiveTab]);

  // Execute SQL with Timeout & Cancellation Abort signals
  // sqlOverride: 查询动作系统传入的 compiledSql，优先于编辑器中的 sourceText
  const handleExecuteSql = useCallback(async (timeoutMs: number = 30000, sqlOverride?: string) => {
    const sqlToExecute = sqlOverride ?? activeEditorTab?.sql ?? "";
    if (!sqlToExecute.trim()) return;
    const tabId = activeEditorTab!.id;

    // Double confirmation for PROD environment
    if (datasource.env === "prod") {
      const confirmed = await requestConfirm(
        "生产环境操作确认",
        `您正在对【生产环境 (PROD)】执行 SQL 操作！\n\n` +
        `数据源: ${datasource.name}\n` +
        `数据库: ${datasource.database_name}\n\n` +
        `线上环境操作可能影响业务性能或触发审计日志。请确认 SQL 语句符合规范。`,
        "danger",
      );
      if (!confirmed) return;
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
      const checked = await api.validateSql(sqlToExecute, { datasourceId: datasource.id, signal: controller.signal });
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
      const result = await api.executeSql(datasource.id, sqlToExecute, undefined, execId, controller.signal);

      clearTimeout(timeoutId);
      updateTabById(tabId, () => ({
        status: "success",
        queryResult: result,
        queryError: null,
        // savedSql intentionally stores the source SQL/DSL text, not the compiled SQL.
        savedSql: activeEditorTab.sql,
      }));

      if (onExecuteSuccess) {
        onExecuteSuccess();
      }
    } catch (error: unknown) {
      clearTimeout(timeoutId);
      const errorCode = getErrorCode(error);
      const isAborted = controller.signal.aborted;
      // Fetch uses abort DOMException, check if custom timeout was passed
      const isTimeout = isAborted && controller.signal.reason === "timeout";

      updateTabById(tabId, () => {
        if (isTimeout || errorCode === "SQL_QUERY_TIMEOUT") {
          return {
            status: "timeout",
            queryError: `查询执行超时 (时间限制: ${timeoutMs / 1000} 秒)`
          };
        } else if (isAborted || errorCode === "SQL_QUERY_CANCELLED") {
          return {
            status: "cancelled",
            queryError: "查询已被用户手动取消。"
          };
        } else {
          return {
            status: "error",
            queryError: getErrorMessage(error, "SQL 执行发生错误")
          };
        }
      });
    } finally {
      if (abortControllersRef.current[tabId] === controller) {
        delete abortControllersRef.current[tabId];
      }
    }
  }, [activeEditorTab, datasource, onExecuteSuccess, requestConfirm, requestServerCancel, updateTabById]);

  // Manual cancellation
  const handleCancelQuery = useCallback((tabId: string) => {
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
  }, [requestServerCancel, tabs, updateTabById]);

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
    openSqlDraft,
    handleCloseTab,
    startRenaming,
    commitRename,
    updateActiveTab,
    handleValidateSql,
    handleExecuteSql,
    handleCancelQuery,
    confirmRequest,
    resolveConfirm,
  };
};
