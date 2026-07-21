import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConsoleExecuteResponse, DataSource } from "../../../lib/api/types";
import { agentApi } from "../../../lib/api/agent";
import { SqlConsoleWorkspace, type ConsoleEntry, type SqlConsoleTabState } from "../SqlConsoleWorkspace";

vi.mock("../../../lib/api/agent", () => ({
  agentApi: {
    executeSqlConsole: vi.fn(),
    fetchArtifactPage: vi.fn(),
    exportArtifactCsv: vi.fn(),
  },
}));

vi.mock("../../../components/SqlEditor", () => ({
  SqlEditor: () => <div data-testid="monaco-editor-mock" />,
}));

const datasource: DataSource = {
  id: "ds-1",
  name: "Local SQLite",
  db_type: "sqlite",
  host: null,
  port: 0,
  database_name: "app.db",
  username: null,
  connection_mode: "direct",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
};

const consoleArtifactResponse: ConsoleExecuteResponse = {
  runId: "console-run-1",
  sessionId: "sql-1",
  sqlArtifactId: "agent/run/console-run-1/artifact/001/sql_query_a1",
  safetyArtifactId: "agent/run/console-run-1/artifact/002/safety_report_a1",
  resultArtifactId: "agent/run/console-run-1/artifact/003/result_view_a1",
  warnings: [],
  notices: [],
  artifacts: [
    {
      id: "agent/run/console-run-1/artifact/001/sql_query_a1",
      semantic_id: "sql_query_a1",
      type: "sql",
      title: "Validated SQL",
      payload: {
        sql: "SELECT 1 AS id, 'Ada' AS name",
        validationStatus: "passed",
        executionStatus: "completed",
        rowCount: 1,
        latencyMs: 7,
      },
      presentation: { mode: "dock", priority: 70, collapsed: true },
      depends_on: [],
    },
    {
      id: "agent/run/console-run-1/artifact/002/safety_report_a1",
      semantic_id: "safety_report_a1",
      type: "safety",
      title: "Safety report",
      payload: {
        passed: true,
        canExecute: true,
        requiresApproval: false,
        safeSql: "SELECT 1 AS id, 'Ada' AS name",
      },
      presentation: { mode: "dock", priority: 75, collapsed: true },
      depends_on: ["agent/run/console-run-1/artifact/001/sql_query_a1"],
    },
    {
      id: "agent/run/console-run-1/artifact/003/result_view_a1",
      semantic_id: "result_view_a1",
      type: "result_view",
      title: "Result view",
      payload: {
        sourceSqlArtifactId: "agent/run/console-run-1/artifact/001/sql_query_a1",
        safetyArtifactId: "agent/run/console-run-1/artifact/002/safety_report_a1",
        queryFingerprint: "query-console-1",
        datasourceGeneration: 1,
        columns: [
          { name: "id", type: "integer" },
          { name: "name", type: "text" },
        ],
        rowCount: 1,
        returnedRows: 1,
        latencyMs: 7,
      },
      presentation: { mode: "both", priority: 20, collapsed: false },
      depends_on: [
        "agent/run/console-run-1/artifact/001/sql_query_a1",
        "agent/run/console-run-1/artifact/002/safety_report_a1",
      ],
    },
  ],
};

function renderConsole(
  initialState: SqlConsoleTabState,
  options: {
    datasources?: DataSource[];
    activeDatasourceId?: string;
    onToast?: (message: string) => void;
  } = {},
) {
  const onToast = options.onToast ?? vi.fn();
  function Harness() {
    const [state, setState] = useState(initialState);
    return (
      <SqlConsoleWorkspace
        tabId="sql-1"
        state={state}
        onPatchState={(_tabId, patch) => setState((current) => ({ ...current, ...patch }))}
        onAppendEntries={(_tabId, entries: ConsoleEntry[]) =>
          setState((current) => ({ ...current, entries: [...current.entries, ...entries] }))
        }
        onToast={onToast}
        datasources={options.datasources ?? [datasource]}
        activeDatasourceId={options.activeDatasourceId ?? "ds-1"}
      />
    );
  }

  return { ...render(<Harness />), onToast };
}

describe("SqlConsoleWorkspace", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(agentApi.executeSqlConsole).mockReset();
    vi.mocked(agentApi.executeSqlConsole).mockResolvedValue(consoleArtifactResponse);
    vi.mocked(agentApi.fetchArtifactPage).mockReset();
    vi.mocked(agentApi.fetchArtifactPage).mockResolvedValue({
      columns: ["id", "name"],
      rows: [{ id: 1, name: "Ada" }],
      page: 1,
      pageSize: 50,
      rowCount: null,
      hasNextPage: false,
      latencyMs: 7,
      consistency: "live_reexecution",
      originalExecutedAt: "2026-07-20T00:00:00Z",
      viewExecutedAt: "2026-07-20T00:00:01Z",
      viewExecutionId: "view-console",
      datasourceGeneration: 1,
      queryFingerprint: "query-console",
      warnings: [],
      notices: [],
    });
    vi.mocked(agentApi.exportArtifactCsv).mockReset();
    vi.mocked(agentApi.exportArtifactCsv).mockResolvedValue(new Blob(["id,name\n1,Ada\n"]));
  });

  it("renders a terminal textarea without the boxed Monaco editor and disables execute for empty SQL", () => {
    const { container } = renderConsole({ draftSql: "   ", entries: [], running: false });

    const editor = screen.getByRole("textbox", { name: "SQL 编辑器" });
    expect(editor).toBeTruthy();
    expect(editor.closest(".sql-console-scroll")).toBeTruthy();
    expect(container.querySelector(".sql-console-editor-inline")).toBeNull();
    expect(screen.queryByTestId("monaco-editor-mock")).toBeNull();
    expect(container.querySelector(".sql-console-editor-shell")).toBeNull();
    expect((screen.getByRole("button", { name: /运行/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("executes the current SQL as artifact-backed result data", async () => {
    renderConsole({ draftSql: "SELECT 1 AS id, 'Ada' AS name", entries: [], running: false });

    fireEvent.click(screen.getByRole("button", { name: /运行/ }));

    await waitFor(() => {
      expect(agentApi.executeSqlConsole).toHaveBeenCalledTimes(1);
      expect(agentApi.executeSqlConsole).toHaveBeenCalledWith({
        datasourceId: "ds-1",
        sql: "SELECT 1 AS id, 'Ada' AS name",
        question: "SQL Console",
        sessionId: "sql-1",
      });
    });
    await waitFor(() => {
      expect(agentApi.fetchArtifactPage).toHaveBeenCalledWith(
        "agent/run/console-run-1/artifact/003/result_view_a1",
        expect.objectContaining({ page: 1, pageSize: 50, countMode: "estimate" }),
        expect.any(AbortSignal),
      );
    });
    expect(await screen.findByText("Ada")).toBeTruthy();
  });

  it("executes selected SQL without clearing the full editor draft", async () => {
    renderConsole({
      draftSql: "SELECT * FROM orders;\nSELECT selected_id FROM orders;",
      entries: [],
      running: false,
    });

    const editor = screen.getByRole("textbox", { name: "SQL 编辑器" }) as HTMLTextAreaElement;
    editor.focus();
    editor.setSelectionRange(22, 52);
    fireEvent.select(editor);
    fireEvent.keyDown(editor, { key: "F9" });

    await waitFor(() => {
      expect(agentApi.executeSqlConsole).toHaveBeenCalledWith({
        datasourceId: "ds-1",
        sql: "SELECT selected_id FROM orders",
        question: "SQL Console",
        sessionId: "sql-1",
      });
    });
    expect(editor.value).toContain("SELECT * FROM orders");
  });

  it("locks editor actions while a query is running", () => {
    renderConsole({ draftSql: "SELECT 1", entries: [], running: true });

    expect((screen.getByRole("textbox", { name: "SQL 编辑器" }) as HTMLTextAreaElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /正在运行/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows datasource readiness, statement guidance, and live SQL highlighting", () => {
    const { container } = renderConsole({
      draftSql: "SELECT COUNT(*) FROM users WHERE name = 'Ada';\nUPDATE users SET active = 0 WHERE id = 10;",
      entries: [],
      running: false,
    });

    const status = screen.getByLabelText("SQL 输入状态");
    expect(status.textContent).toContain("Local SQLite");
    expect(status.textContent).toContain("app.db");
    expect(status.textContent).toContain("SQLite");
    expect(status.textContent).toContain("2 条语句");
    expect(status.textContent).toContain("SELECT");
    expect(status.textContent).toContain("UPDATE");

    const highlight = screen.getByLabelText("SQL 高亮预览");
    expect(highlight.querySelector(".sql-console-statement--read")?.textContent).toContain("SELECT");
    expect(highlight.querySelector(".sql-console-statement--write")?.textContent).toContain("UPDATE");
    expect(container.querySelector(".sql-console-token-keyword")?.textContent).toBe("SELECT");
    expect(container.querySelector(".sql-console-token-function")?.textContent).toBe("COUNT");
    expect(container.querySelector(".sql-console-token-string")?.textContent).toBe("'Ada'");
    expect(container.querySelector(".sql-console-token-number")?.textContent).toBe("0");
  });

  it("disables execution and warns when the requested datasource is unavailable", () => {
    const { onToast } = renderConsole(
      { draftSql: "SELECT 1", entries: [], running: false },
      { datasources: [], activeDatasourceId: "missing-ds" },
    );

    expect(screen.getByLabelText("SQL 输入状态").textContent).toContain("绑定的数据源不可用");
    expect((screen.getByRole("button", { name: /运行/ }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /运行/ }));

    expect(agentApi.executeSqlConsole).not.toHaveBeenCalled();
    expect(onToast).not.toHaveBeenCalled();
  });
});
