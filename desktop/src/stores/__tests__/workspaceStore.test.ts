import { beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkspaceStore } from "../workspaceStore";

const INITIAL = {
  tabs: [{ id: "smart-query", title: "问数工作台", type: "smart-query" as const }],
  activeTabId: "smart-query",
  sqlConsoleState: {},
  selectedTables: [],
  contextTables: [],
  tableSubTabs: {},
  _tabSeq: { sql: 1, multiTable: 1, queryResult: 1, message: 1 },
};

function reset() {
  useWorkspaceStore.setState(INITIAL);
}

describe("workspaceStore — tabs", () => {
  beforeEach(reset);

  it("openSqlConsole adds a new sql tab and activates it", () => {
    useWorkspaceStore.getState().openSqlConsole("SELECT 1");
    const s = useWorkspaceStore.getState();
    expect(s.tabs).toHaveLength(2);
    expect(s.tabs[1].type).toBe("sql");
    expect(s.activeTabId).toBe("sql-1");
    expect(s.sqlConsoleState["sql-1"].draftSql).toBe("SELECT 1");
  });

  it("closeTab removes the tab and clears its console state", () => {
    useWorkspaceStore.getState().openSqlConsole();
    useWorkspaceStore.getState().closeTab("sql-1");
    const s = useWorkspaceStore.getState();
    expect(s.tabs.find((t) => t.id === "sql-1")).toBeUndefined();
    expect(s.sqlConsoleState["sql-1"]).toBeUndefined();
  });

  it("closeTab restores the default tab when all tabs are gone", () => {
    useWorkspaceStore.getState().closeTab("smart-query");
    const s = useWorkspaceStore.getState();
    expect(s.tabs).toHaveLength(1);
    expect(s.tabs[0].id).toBe("smart-query");
    expect(s.activeTabId).toBe("smart-query");
  });

  it("setTabs accepts an updater function", () => {
    useWorkspaceStore.getState().setTabs((prev) => [...prev, { id: "x", title: "X", type: "llm-config" }]);
    expect(useWorkspaceStore.getState().tabs.find((t) => t.id === "x")).toBeDefined();
  });

  it("patchTab merges a partial update into a single tab", () => {
    useWorkspaceStore.getState().patchTab("smart-query", { agentStatus: "running" });
    expect(useWorkspaceStore.getState().tabs[0].agentStatus).toBe("running");
  });

  it("openDiagnosticsTab opens a single diagnostics tab and activates it", () => {
    useWorkspaceStore.getState().openDiagnosticsTab();
    useWorkspaceStore.getState().openDiagnosticsTab();

    const s = useWorkspaceStore.getState();
    const diagnosticTabs = s.tabs.filter((t) => t.type === "diagnostics");
    expect(diagnosticTabs).toHaveLength(1);
    expect(diagnosticTabs[0].id).toBe("diagnostics");
    expect(diagnosticTabs[0].title).toBe("诊断日志");
    expect(s.activeTabId).toBe("diagnostics");
  });
});

describe("workspaceStore — messages", () => {
  beforeEach(reset);

  it("appendTabMessages adds messages to a tab's chat", () => {
    useWorkspaceStore.getState().appendTabMessages("smart-query", [
      { id: 1, sender: "user", text: "hi" },
    ]);
    const tab = useWorkspaceStore.getState().tabs[0];
    expect(tab.chatMessages?.map((m) => m.text)).toEqual(["hi"]);
  });

  it("updateTabMessage rewrites an existing message's text", () => {
    useWorkspaceStore.getState().appendTabMessages("smart-query", [{ id: 1, sender: "ai", text: "old" }]);
    useWorkspaceStore.getState().updateTabMessage("smart-query", 1, "new");
    expect(useWorkspaceStore.getState().tabs[0].chatMessages?.[0].text).toBe("new");
  });

  it("_nextMsgId returns increasing ids and advances the sequence", () => {
    const a = useWorkspaceStore.getState()._nextMsgId();
    const b = useWorkspaceStore.getState()._nextMsgId();
    expect(b).toBe(a + 1);
  });
});

describe("workspaceStore — context tables", () => {
  beforeEach(reset);

  it("addContextTable dedupes and keeps order", () => {
    useWorkspaceStore.getState().addContextTable("users");
    useWorkspaceStore.getState().addContextTable("orders");
    useWorkspaceStore.getState().addContextTable("users");
    expect(useWorkspaceStore.getState().contextTables).toEqual(["users", "orders"]);
  });

  it("removeContextTable drops only the named table", () => {
    useWorkspaceStore.getState().addContextTable("users");
    useWorkspaceStore.getState().addContextTable("orders");
    useWorkspaceStore.getState().removeContextTable("users");
    expect(useWorkspaceStore.getState().contextTables).toEqual(["orders"]);
  });

  it("clearContextTables empties the list", () => {
    useWorkspaceStore.getState().addContextTable("users");
    useWorkspaceStore.getState().clearContextTables();
    expect(useWorkspaceStore.getState().contextTables).toEqual([]);
  });
});

describe("workspaceStore — conversations", () => {
  beforeEach(reset);

  it("openConversationResult opens a lightweight conversation tab", () => {
    useWorkspaceStore.getState().openConversationResult({ id: "conv-1", title: "Orders" });
    useWorkspaceStore.getState().openConversationResult({ id: "conv-1", title: "Orders" });

    const state = useWorkspaceStore.getState();
    const tabs = state.tabs.filter((tab) => tab.id === "conversation-conv-1");
    expect(tabs).toHaveLength(1);
    expect(tabs[0].type).toBe("query-result");
    expect(tabs[0].conversationId).toBe("conv-1");
    expect(state.activeTabId).toBe("conversation-conv-1");
  });
});
