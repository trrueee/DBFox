import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditorView } from "@codemirror/view";
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

vi.mock("../../../lib/api/schema", () => ({
  schemaApi: {
    listTables: vi.fn().mockResolvedValue([]),
    listColumns: vi.fn().mockResolvedValue([]),
  },
}));

const datasource: DataSource = {
  id: "ds-1",
  name: "Local SQLite",
  db_type: "sqlite",
  env: "dev",
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
      session_id: "sql-1",
      run_id: "console-run-1",
      turn_id: null,
      semantic_key: "sql_query_a1",
      version: 1,
      type: "sql",
      title: "Validated SQL",
      status: "completed",
      visibility: "supporting",
      summary: null,
      payload: {
        sql: "SELECT 1 AS id, 'Ada' AS name",
        validationStatus: "passed",
        executionStatus: "completed",
        rowCount: 1,
        latencyMs: 7,
      },
      payload_ref: null,
      provenance: {},
      relations: [],
    },
    {
      id: "agent/run/console-run-1/artifact/002/safety_report_a1",
      session_id: "sql-1",
      run_id: "console-run-1",
      turn_id: null,
      semantic_key: "safety_report_a1",
      version: 1,
      type: "safety",
      title: "Safety report",
      status: "completed",
      visibility: "internal",
      summary: null,
      payload: {
        passed: true,
        canExecute: true,
        requiresApproval: false,
        safeSql: "SELECT 1 AS id, 'Ada' AS name",
      },
      payload_ref: null,
      provenance: {},
      relations: [
        {
          relation: "supports",
          artifact_id: "agent/run/console-run-1/artifact/001/sql_query_a1",
        },
      ],
    },
    {
      id: "agent/run/console-run-1/artifact/003/result_view_a1",
      session_id: "sql-1",
      run_id: "console-run-1",
      turn_id: null,
      semantic_key: "result_view_a1",
      version: 1,
      type: "result_view",
      title: "Result view",
      status: "completed",
      visibility: "primary",
      summary: null,
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
      payload_ref: null,
      provenance: {},
      relations: [
        {
          relation: "derived_from",
          artifact_id: "agent/run/console-run-1/artifact/001/sql_query_a1",
        },
        {
          relation: "validated_by",
          artifact_id: "agent/run/console-run-1/artifact/002/safety_report_a1",
        },
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
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Harness() {
    const [state, setState] = useState(initialState);
    return (
      <QueryClientProvider client={queryClient}>
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
      </QueryClientProvider>
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

  it("renders the CodeMirror SQL editor and disables execute for empty SQL", () => {
    const { container } = renderConsole({ draftSql: "   ", entries: [], running: false });

    const editor = screen.getByRole("textbox", { name: "SQL 编辑器" });
    expect(editor).toBeTruthy();
    expect(editor.closest(".sql-console-editor")).toBeTruthy();
    expect(editor.closest(".sql-console-command-row")).toBeTruthy();
    expect(screen.getByRole("region", { name: "SQL 命令行控制台" })).toBeTruthy();
    expect(screen.queryByRole("separator", { name: /结果面板/ })).toBeNull();
    expect(container.querySelector(".sql-console-transcript")).toBeTruthy();
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
        question: "SQL 控制台",
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
    const terminal = screen.getByRole("region", { name: "SQL 命令行控制台" });
    expect(terminal.textContent).toContain("SELECT 1 AS id, 'Ada' AS name");
    expect(terminal.textContent).toContain("Ada");
    expect(screen.getByText("SQL 控制台已就绪，输入语句后按 F9 或 Ctrl+Enter 执行。")).toBeTruthy();
    expect(screen.getByText("SELECT 1 AS id, 'Ada' AS name")).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /结果/ })).toBeNull();
    expect(screen.queryByRole("separator", { name: /结果面板/ })).toBeNull();
  });

  it("keeps command history and results in one transcript and clears them together", async () => {
    renderConsole({ draftSql: "SELECT 1 AS id, 'Ada' AS name", entries: [], running: false });

    fireEvent.click(screen.getByRole("button", { name: /运行/ }));
    expect(await screen.findByText("Ada")).toBeTruthy();
    expect(screen.getByText("SELECT 1 AS id, 'Ada' AS name")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "清屏" }));

    expect(screen.getByText("控制台已清屏。")).toBeTruthy();
    expect(screen.queryByText("Ada")).toBeNull();
    expect(screen.queryByText("SELECT 1 AS id, 'Ada' AS name")).toBeNull();
    expect(screen.getByRole("textbox", { name: "SQL 编辑器" })).toBeTruthy();
  });

  it("executes selected SQL without clearing the full editor draft", async () => {
    renderConsole({
      draftSql: "SELECT * FROM orders;\nSELECT selected_id FROM orders;",
      entries: [],
      running: false,
    });

    const editor = screen.getByRole("textbox", { name: "SQL 编辑器" });
    const editorView = EditorView.findFromDOM(editor as HTMLElement);
    expect(editorView).toBeTruthy();
    editorView!.dispatch({ selection: { anchor: 22, head: 52 } });
    fireEvent.keyDown(editor, { key: "F9" });

    await waitFor(() => {
      expect(agentApi.executeSqlConsole).toHaveBeenCalledWith({
        datasourceId: "ds-1",
        sql: "SELECT selected_id FROM orders",
        question: "SQL 控制台",
        sessionId: "sql-1",
      });
    });
    expect(editorView!.state.doc.toString()).toContain("SELECT * FROM orders");
  });

  it("locks editor actions while a query is running", () => {
    renderConsole({ draftSql: "SELECT 1", entries: [], running: true });

    expect(screen.getByRole("textbox", { name: "SQL 编辑器" }).getAttribute("aria-readonly")).toBe("true");
    expect((screen.getByRole("button", { name: /正在运行/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows datasource readiness, statement guidance, and live SQL highlighting", () => {
    const { container } = renderConsole({
      draftSql: "SELECT COUNT(*) FROM users WHERE name = 'Ada';\nUPDATE users SET active = 0 WHERE id = 10;",
      entries: [],
      running: false,
    });

    const status = screen.getByLabelText("SQL 输入状态");
    expect(screen.getByText("Local SQLite · app.db · SQLite")).toBeTruthy();
    expect(status.textContent).toContain("2 条语句");
    expect(status.textContent).toContain("SELECT");
    expect(status.textContent).toContain("UPDATE");

    expect(container.querySelector(".cm-content")?.textContent).toContain("SELECT COUNT(*)");
    expect(container.querySelector(".tok-keyword")?.textContent?.toUpperCase()).toBe("SELECT");
    expect(container.querySelector(".tok-string")?.textContent).toBe("'Ada'");
    expect(container.querySelector(".tok-number")?.textContent).toBe("0");
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
