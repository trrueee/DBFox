import { beforeEach, describe, expect, it, vi } from "vitest";
import { useWorkspaceStore } from "../workspaceStore";
import type { Conversation } from "../../types/conversation";

vi.mock("../../features/conversation/conversationRepository", () => ({
  deleteConversation: vi.fn(),
  listConversations: vi.fn(),
  saveConversation: vi.fn(),
}));

// Re-import the mocked module so we can assert on the fns.
const { saveConversation, listConversations, deleteConversation } = await import(
  "../../features/conversation/conversationRepository"
);

const INITIAL = {
  tabs: [{ id: "smart-query", title: "问数工作台", type: "smart-query" as const }],
  activeTabId: "smart-query",
  sqlConsoleState: {},
  selectedTables: [],
  contextTables: [],
  tableSubTabs: {},
  conversations: [],
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
  beforeEach(() => {
    reset();
    vi.mocked(saveConversation).mockReset();
    vi.mocked(listConversations).mockReset();
    vi.mocked(deleteConversation).mockReset();
  });

  it("persistConversation calls saveConversation and prepends to state", async () => {
    vi.mocked(saveConversation).mockResolvedValue(undefined);
    const conv: Conversation = {
      id: "c1",
      title: "T",
      createdAt: 100,
      updatedAt: 100,
      contextTables: [],
      messages: [],
      artifacts: [],
    };
    await useWorkspaceStore.getState().persistConversation(conv);
    expect(saveConversation).toHaveBeenCalledWith(conv);
    expect(useWorkspaceStore.getState().conversations.map((c) => c.id)).toEqual(["c1"]);
  });

  it("persistConversation keeps the newest copy when id already exists", async () => {
    vi.mocked(saveConversation).mockResolvedValue(undefined);
    const base: Conversation = {
      id: "c1",
      title: "old",
      createdAt: 100,
      updatedAt: 100,
      contextTables: [],
      messages: [],
      artifacts: [],
    };
    await useWorkspaceStore.getState().persistConversation(base);
    await useWorkspaceStore.getState().persistConversation({ ...base, title: "new", updatedAt: 200 });
    const convs = useWorkspaceStore.getState().conversations;
    expect(convs).toHaveLength(1);
    expect(convs[0].title).toBe("new");
  });

  it("deleteConversationById calls deleteConversation and removes from state", async () => {
    vi.mocked(deleteConversation).mockResolvedValue(undefined);
    vi.mocked(saveConversation).mockResolvedValue(undefined);
    await useWorkspaceStore.getState().persistConversation({
      id: "c1",
      title: "T",
      createdAt: 100,
      updatedAt: 100,
      contextTables: [],
      messages: [],
      artifacts: [],
    });
    await useWorkspaceStore.getState().deleteConversationById("c1");
    expect(deleteConversation).toHaveBeenCalledWith("c1");
    expect(useWorkspaceStore.getState().conversations).toHaveLength(0);
  });

  it("initConversations loads history via listConversations", async () => {
    const history: Conversation[] = [
      { id: "h1", title: "H1", createdAt: 1, updatedAt: 1, contextTables: [], messages: [], artifacts: [] },
    ];
    vi.mocked(listConversations).mockResolvedValue(history);
    await useWorkspaceStore.getState().initConversations();
    expect(listConversations).toHaveBeenCalled();
    expect(useWorkspaceStore.getState().conversations).toEqual(history);
  });
});
