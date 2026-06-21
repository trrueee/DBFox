import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAgentStore } from "../agentStore";
import { useWorkspaceStore } from "../workspaceStore";
import { useDatasourceStore } from "../datasourceStore";

vi.mock("../../lib/api/agent", () => ({
  agentApi: {
    streamAgentQuery: vi.fn(),
    cancelAgentRun: vi.fn(),
  },
  resolveAgentApproval: vi.fn(),
  streamResumeAgentRun: vi.fn(),
  mergeArtifactDelta: vi.fn((artifacts) => artifacts),
}));

vi.mock("../../components/SettingsDialog", () => ({
  getStoredApiConfig: vi.fn(() => ({ apiKey: "test-key", apiBase: "", modelName: "gpt-4o" })),
}));

vi.mock("../../features/workspace/agentTimeline", () => ({
  createInitialAgentTimeline: vi.fn(() => []),
  appendAgentRuntimeEvent: vi.fn((timeline) => timeline),
  timelineFromFinalResponse: vi.fn((timeline) => timeline),
}));

vi.mock("../../features/workspace/agentBridge", () => ({
  buildAnswerText: vi.fn(() => "mocked answer"),
  buildSuggestionsText: vi.fn(() => ""),
  describeRuntimeEvent: vi.fn(() => ""),
  mergeApiArtifacts: vi.fn((_a, b) => b || []),
  toViewArtifacts: vi.fn(() => []),
}));

const { agentApi } = await import("../../lib/api/agent");

function resetAll() {
  useAgentStore.setState({
    _abortControllers: new Map(),
    _runIds: new Map(),
    _cancelledTabs: new Set(),
  });
  useWorkspaceStore.setState({
    tabs: [{ id: "smart-query", title: "问数工作台", type: "smart-query" as const }],
    activeTabId: "smart-query",
    sqlConsoleState: {},
    selectedTables: [],
    contextTables: [],
    tableSubTabs: {},
    conversations: [],
    _tabSeq: { sql: 1, multiTable: 1, queryResult: 1, message: 1 },
  });
  useDatasourceStore.setState({
    datasources: [],
    activeDatasourceId: "ds-1",
    activeDatasourceForSettings: null,
    tables: [],
    loadingSchema: false,
    schemaError: "",
    tableColumns: {},
  });
}

describe("agentStore — cancelAgentRun", () => {
  beforeEach(() => {
    resetAll();
    vi.mocked(agentApi.cancelAgentRun).mockReset();
  });

  it("calls agentApi.cancelAgentRun with the stored runId", async () => {
    vi.mocked(agentApi.cancelAgentRun).mockResolvedValue(undefined as never);
    useAgentStore.getState()._runIds.set("tab-1", "run-abc");

    await useAgentStore.getState().cancelAgentRun("tab-1");

    expect(agentApi.cancelAgentRun).toHaveBeenCalledWith("run-abc");
  });

  it("adds tab to _cancelledTabs", async () => {
    vi.mocked(agentApi.cancelAgentRun).mockResolvedValue(undefined as never);
    useAgentStore.getState()._runIds.set("tab-1", "run-abc");

    await useAgentStore.getState().cancelAgentRun("tab-1");

    expect(useAgentStore.getState()._cancelledTabs.has("tab-1")).toBe(true);
  });

  it("aborts the controller and cleans up", async () => {
    vi.mocked(agentApi.cancelAgentRun).mockResolvedValue(undefined as never);
    const controller = new AbortController();
    useAgentStore.getState()._abortControllers.set("tab-1", controller);
    useAgentStore.getState()._runIds.set("tab-1", "run-abc");
    const spy = vi.spyOn(controller, "abort");

    await useAgentStore.getState().cancelAgentRun("tab-1");

    expect(spy).toHaveBeenCalled();
    expect(useAgentStore.getState()._abortControllers.has("tab-1")).toBe(false);
    expect(useAgentStore.getState()._runIds.has("tab-1")).toBe(false);
  });

  it("sets agentStatus to failed on the tab", async () => {
    vi.mocked(agentApi.cancelAgentRun).mockResolvedValue(undefined as never);
    useWorkspaceStore.getState().patchTab("smart-query", { agentStatus: "running" });

    await useAgentStore.getState().cancelAgentRun("smart-query");

    const tab = useWorkspaceStore.getState().tabs.find((t) => t.id === "smart-query");
    expect(tab?.agentStatus).toBe("failed");
  });
});

describe("agentStore — sendFollowUp", () => {
  beforeEach(resetAll);

  it("appends user message and triggers runAgentForTab", () => {
    const runSpy = vi.fn().mockResolvedValue(undefined);
    useAgentStore.setState({ runAgentForTab: runSpy } as never);

    useAgentStore.getState().sendFollowUp("smart-query", "hello");

    const tab = useWorkspaceStore.getState().tabs[0];
    const lastMsg = tab.chatMessages?.slice(-1)?.[0];
    expect(lastMsg?.text).toBe("hello");
    expect(lastMsg?.sender).toBe("user");
  });

  it("ignores empty text", () => {
    const runSpy = vi.fn();
    useAgentStore.setState({ runAgentForTab: runSpy } as never);

    useAgentStore.getState().sendFollowUp("smart-query", "  ");
    useAgentStore.getState().sendFollowUp("smart-query", "");

    expect(runSpy).not.toHaveBeenCalled();
  });
});

describe("agentStore — regenerateAgentRun", () => {
  beforeEach(resetAll);

  it("re-runs with the original user question", () => {
    const runSpy = vi.fn().mockResolvedValue(undefined);
    useAgentStore.setState({ runAgentForTab: runSpy } as never);
    useWorkspaceStore.getState().appendTabMessages("smart-query", [
      { id: 1, sender: "user", text: "original question" },
    ]);

    useAgentStore.getState().regenerateAgentRun("smart-query");

    expect(runSpy).toHaveBeenCalledWith("smart-query", "original question", {
      sessionId: undefined,
      parentRunId: undefined,
    });
  });
});
