import { useCallback, useMemo, useState } from "react";
import type { DataSource } from "../../lib/api";
import type { QueryTabStatePatch, TableSubTab, WorkbenchAction, WorkbenchTab } from "./types";

function makeId(prefix: string) {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  return `${prefix}:${random}`;
}

export function useWorkbenchTabs(activeDataSource: DataSource | null) {
  const [tabs, setTabs] = useState<WorkbenchTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  const activeTab = useMemo(
    () => tabs.find((tab) => tab.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );

  const openQueryTab = useCallback((sqlDraft = "", title?: string) => {
    const id = makeId("query");
    const nextTab: WorkbenchTab = {
      id,
      type: "query",
      title: title || `SQL ${tabs.filter((tab) => tab.type === "query").length + 1}`,
      sqlDraft,
      connectionId: activeDataSource?.id,
      databaseName: activeDataSource?.database_name,
      closable: true,
      resultState: "idle",
    };
    setTabs((prev) => [...prev, nextTab]);
    setActiveTabId(id);
  }, [activeDataSource?.database_name, activeDataSource?.id, tabs]);

  const openTableTab = useCallback((tableName: string, subTab: TableSubTab = "data") => {
    const id = `table:${activeDataSource?.id ?? "none"}:${tableName}`;
    setTabs((prev) => {
      const exists = prev.some((tab) => tab.id === id);
      if (exists) {
        return prev.map((tab) => tab.id === id ? { ...tab, activeSubTab: subTab } : tab);
      }
      const nextTab: WorkbenchTab = {
        id,
        type: "table",
        title: tableName,
        tableName,
        activeSubTab: subTab,
        connectionId: activeDataSource?.id,
        databaseName: activeDataSource?.database_name,
        closable: true,
      };
      return [...prev, nextTab];
    });
    setActiveTabId(id);
  }, [activeDataSource?.database_name, activeDataSource?.id]);

  const closeTab = useCallback((id: string) => {
    setTabs((prev) => {
      const nextTabs = prev.filter((tab) => tab.id !== id);
      setActiveTabId((current) => {
        if (current !== id) return current;
        return nextTabs[nextTabs.length - 1]?.id ?? null;
      });
      return nextTabs;
    });
  }, []);

  const closeOtherTabs = useCallback(() => {
    if (!activeTabId) return;
    setTabs((prev) => prev.filter((tab) => tab.id === activeTabId));
  }, [activeTabId]);

  const closeTabsToRight = useCallback(() => {
    if (!activeTabId) return;
    setTabs((prev) => {
      const index = prev.findIndex((tab) => tab.id === activeTabId);
      return index === -1 ? prev : prev.slice(0, index + 1);
    });
  }, [activeTabId]);

  const switchTableSubTab = useCallback((tabId: string, subTab: TableSubTab) => {
    setTabs((prev) => prev.map((tab) => tab.id === tabId ? { ...tab, activeSubTab: subTab } : tab));
  }, []);

  const updateActiveQueryState = useCallback((state: QueryTabStatePatch) => {
    if (!activeTabId) return;
    setTabs((prev) => prev.map((tab) => {
      if (tab.id !== activeTabId) return tab;
      const nextResultState = state.resultState ?? tab.resultState;
      const nextSqlDraft = state.sqlDraft ?? tab.sqlDraft;
      const nextDirty = state.dirty ?? tab.dirty;
      const nextLastQueryResultPreview = state.lastQueryResultPreview ?? tab.lastQueryResultPreview;
      const nextLastError = state.lastError ?? tab.lastError;
      const terminalResult =
        nextResultState &&
        nextResultState !== tab.resultState &&
        ["success", "error", "timeout", "cancelled"].includes(nextResultState);

      return {
        ...tab,
        resultState: nextResultState,
        sqlDraft: nextSqlDraft,
        dirty: nextDirty,
        lastQueryResultPreview: nextLastQueryResultPreview,
        lastError: nextLastError,
        lastExecutedAt: terminalResult ? Date.now() : tab.lastExecutedAt,
      };
    }));
  }, [activeTabId]);

  const applySqlToActiveEditor = useCallback((sql: string) => {
    const trimmed = sql.trim();
    if (!trimmed) return false;
    if (!activeTabId || activeTab?.type !== "query") return false;
    setTabs((prev) => prev.map((tab) => tab.id === activeTabId ? { ...tab, sqlDraft: trimmed, dirty: true } : tab));
    return true;
  }, [activeTab?.type, activeTabId]);

  const triggerActiveAction = useCallback((actionType: WorkbenchAction) => {
    if (!activeTabId) return;
    setTabs((prev) => prev.map((tab) => tab.id === activeTabId ? {
      ...tab,
      actionTrigger: {
        type: actionType,
        nonce: Date.now(),
      },
    } : tab));
  }, [activeTabId]);

  return {
    tabs,
    activeTab,
    activeTabId,
    setActiveTabId,
    openQueryTab,
    openTableTab,
    closeTab,
    closeOtherTabs,
    closeTabsToRight,
    switchTableSubTab,
    updateActiveQueryState,
    applySqlToActiveEditor,
    triggerActiveAction,
  };
}
