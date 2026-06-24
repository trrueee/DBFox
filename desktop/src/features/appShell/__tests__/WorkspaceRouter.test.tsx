import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceRouter } from "../WorkspaceRouter";
import { useDatasourceStore } from "../../../stores/datasourceStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import type { WorkspaceTab } from "../../../types/workspace";

const tableWorkspaceProps = vi.hoisted(() => ({
  latest: null as Record<string, unknown> | null,
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
  DataSourcesPage: () => <div data-testid="datasources-page" />,
}));
vi.mock("../../../pages/DiagnosticsPage", () => ({
  DiagnosticsPage: () => <div data-testid="diagnostics-page" />,
}));
vi.mock("../../../components/SettingsDialog", () => ({
  useApiConfig: () => ({
    config: {},
    updateConfig: vi.fn(),
    handleSave: vi.fn(),
  }),
}));
vi.mock("../../../components/LlmConfigPanel", () => ({
  LlmConfigPanel: () => <div data-testid="llm-config" />,
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
