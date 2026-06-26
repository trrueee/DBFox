import { cleanup, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceRouter } from "../WorkspaceRouter";
import { useDatasourceStore } from "../../../stores/datasourceStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { WorkspaceTab } from "../../../types/workspace";

const tableWorkspaceProps = vi.hoisted(() => ({
  latest: null as Record<string, unknown> | null,
}));

const workspacePageProps = vi.hoisted(() => ({
  diagnostics: null as Record<string, unknown> | null,
  datasourceSettings: null as Record<string, unknown> | null,
  llmConfig: null as Record<string, unknown> | null,
}));

vi.mock("../../workspace/SmartQueryHome", () => ({
  SmartQueryHome: () => <div data-testid="smart-query-home" />,
}));
vi.mock("../../conversation/ConversationHistoryPanel", () => ({
  ConversationHistoryPanel: () => <div data-testid="conversation-history" />,
}));
vi.mock("../../conversation/workspace/ConversationWorkspace", () => ({
  ConversationWorkspace: () => <div data-testid="conversation-workspace" />,
}));
vi.mock("../../workspace/TableWorkspace", () => ({
  TableWorkspace: (props: Record<string, unknown>) => {
    tableWorkspaceProps.latest = props;
    return (
      <div
        data-testid="table-workspace"
        data-datasource-id={String(props.datasourceId ?? "")}
        data-db-type={String(props.datasourceDbType ?? "")}
      />
    );
  },
}));
vi.mock("../../workspace/SqlConsoleWorkspace", () => ({
  SqlConsoleWorkspace: () => <div data-testid="sql-console" />,
}));
vi.mock("../../workspace/MultiTableWorkspace", () => ({
  MultiTableWorkspace: () => <div data-testid="multi-table" />,
}));
vi.mock("../../workspace/artifacts/TableArtifactView", () => ({
  TableArtifactView: () => <div data-testid="table-artifact" />,
}));
vi.mock("../../../pages/AgentEvalPage", () => ({
  AgentEvalPage: () => <div data-testid="agent-eval" />,
}));
vi.mock("../../../pages/DataSourcesPage", () => ({
  DataSourcesPage: (props: Record<string, unknown>) => {
    workspacePageProps.datasourceSettings = props;
    return <div data-testid="datasources-page" />;
  },
}));
vi.mock("../../../pages/DiagnosticsPage", () => ({
  DiagnosticsPage: (props: Record<string, unknown>) => {
    workspacePageProps.diagnostics = props;
    return <div data-testid="diagnostics-page" />;
  },
}));
vi.mock("../../../components/SettingsDialog", () => ({
  useApiConfig: () => ({
    config: {},
    updateConfig: vi.fn(),
    handleSave: vi.fn(),
  }),
}));
vi.mock("../../../components/LlmConfigPanel", () => ({
  LlmConfigPanel: (props: Record<string, unknown>) => {
    workspacePageProps.llmConfig = props;
    return <div data-testid="llm-config" />;
  },
}));
vi.mock("../../../lib/api/agent", () => ({
  testLlmConnection: vi.fn(),
}));

const DS1 = {
  id: "ds-1",
  name: "Local Postgres",
  db_type: "postgresql",
  host: "localhost",
  port: 5432,
  database_name: "app",
  username: "reader",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
};

const DS2 = {
  id: "ds-2",
  name: "Prod MySQL",
  db_type: "mysql",
  host: "prod",
  port: 3306,
  database_name: "app",
  username: "reader",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
};

describe("WorkspaceRouter table tabs", () => {
  beforeEach(() => {
    cleanup();
    tableWorkspaceProps.latest = null;
    useWorkspaceStore.setState({
      tabs: [{ id: "smart-query", title: "Ask", type: "smart-query" }],
      activeTabId: "smart-query",
      sqlConsoleState: {},
      selectedTables: [],
      contextTables: [],
      tableSubTabs: {},
      _tabSeq: { sql: 1, multiTable: 1, queryResult: 1, message: 1 },
    });
    useDatasourceStore.setState({
      datasources: [DS1, DS2] as never,
      activeDatasourceId: "ds-2",
      activeDatasourceForSettings: DS2 as never,
      tables: [],
      loadingSchema: false,
      schemaError: "",
      tableColumns: {},
    });
  });

  it("uses the datasource captured on the table tab instead of the current active datasource", () => {
    const activeTab: WorkspaceTab = {
      id: "table-ds-1-users",
      title: "users",
      type: "table",
      tableId: "users",
      datasourceId: "ds-1",
      datasourceDbType: "postgresql",
    };

    render(<WorkspaceRouter activeTab={activeTab} showToast={vi.fn()} />);

    expect(screen.getByTestId("table-workspace").getAttribute("data-datasource-id")).toBe("ds-1");
    expect(screen.getByTestId("table-workspace").getAttribute("data-db-type")).toBe("postgresql");
    expect(tableWorkspaceProps.latest).toMatchObject({
      tableId: "users",
      datasourceId: "ds-1",
      datasourceDbType: "postgresql",
    });
  });
});

describe("WorkspaceRouter desktop shell tabs", () => {
  beforeEach(() => {
    cleanup();
    workspacePageProps.diagnostics = null;
    workspacePageProps.datasourceSettings = null;
    workspacePageProps.llmConfig = null;
    useWorkspaceStore.setState({
      tabs: [{ id: "smart-query", title: "Ask", type: "smart-query" }],
      activeTabId: "smart-query",
      sqlConsoleState: {},
      selectedTables: [],
      contextTables: [],
      tableSubTabs: {},
      _tabSeq: { sql: 1, multiTable: 1, queryResult: 1, message: 1 },
    });
    useDatasourceStore.setState({
      datasources: [DS1, DS2] as never,
      activeDatasourceId: "ds-2",
      activeDatasourceForSettings: DS2 as never,
      tables: [],
      loadingSchema: false,
      schemaError: "",
      tableColumns: {},
    });
  });

  it.each([
    [
      "diagnostics",
      { id: "diagnostics", title: "Diagnostics", type: "diagnostics" } as WorkspaceTab,
      "diagnostics-page",
    ],
    [
      "datasource settings",
      { id: "datasource-settings", title: "Data Sources", type: "datasource-settings" } as WorkspaceTab,
      "datasources-page",
    ],
    [
      "llm config",
      { id: "llm-config", title: "LLM Config", type: "llm-config" } as WorkspaceTab,
      "llm-config",
    ],
    [
      "artifact result",
      {
        id: "artifact-result",
        title: "Query Artifact",
        type: "artifact-result",
        artifactResult: { id: "artifact-1", title: "Query Artifact" },
      } as unknown as WorkspaceTab,
      "table-artifact",
    ],
  ])("wraps %s in WorkspaceShell chrome", (_label, activeTab, testId) => {
    render(<WorkspaceRouter activeTab={activeTab} showToast={vi.fn()} />);

    const shell = screen.getByRole("region", { name: activeTab.title });
    expect(within(shell).getByRole("heading", { name: activeTab.title })).toBeTruthy();
    expect(within(shell).getByTestId(testId)).toBeTruthy();
  });

  it("passes workspace chrome to pages that already sit inside WorkspaceShell", () => {
    render(<WorkspaceRouter activeTab={{ id: "diagnostics", title: "Diagnostics", type: "diagnostics" }} showToast={vi.fn()} />);
    expect(workspacePageProps.diagnostics).toMatchObject({ chrome: "workspace" });

    cleanup();
    render(<WorkspaceRouter activeTab={{ id: "datasource-settings", title: "Data Sources", type: "datasource-settings" }} showToast={vi.fn()} />);
    expect(workspacePageProps.datasourceSettings).toMatchObject({ chrome: "workspace" });

    cleanup();
    render(<WorkspaceRouter activeTab={{ id: "llm-config", title: "LLM Config", type: "llm-config" }} showToast={vi.fn()} />);
    expect(workspacePageProps.llmConfig).toMatchObject({ chrome: "workspace" });
  });
});
