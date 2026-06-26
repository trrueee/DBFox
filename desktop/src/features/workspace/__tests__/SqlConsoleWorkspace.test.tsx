import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DataSource } from "../../../lib/api/types";
import { executeSql } from "../../engine/engineApi";
import { SqlConsoleWorkspace, type ConsoleEntry, type SqlConsoleTabState } from "../SqlConsoleWorkspace";

vi.mock("../../engine/engineApi", () => ({
  executeSql: vi.fn(),
}));

vi.mock("../../../components/SqlEditor", () => ({
  SqlEditor: ({
    value,
    onChange,
    onExecute,
    onSelectionChange,
    disabled,
    testId = "sql-console-editor",
  }: {
    value: string;
    onChange: (value: string) => void;
    onExecute?: (sql?: string) => void;
    onSelectionChange?: (sql: string) => void;
    disabled?: boolean;
    testId?: string;
  }) => (
    <div>
      <textarea
        aria-label="SQL 编辑器"
        data-testid={testId}
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button type="button" onClick={() => onExecute?.()}>
        mock-run-all
      </button>
      <button
        type="button"
        onClick={() => {
          onSelectionChange?.("SELECT selected_id FROM orders");
          onExecute?.("SELECT selected_id FROM orders");
        }}
      >
        mock-run-selection
      </button>
    </div>
  ),
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

function renderConsole(initialState: SqlConsoleTabState) {
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
        onToast={vi.fn()}
        datasources={[datasource]}
        activeDatasourceId="ds-1"
      />
    );
  }

  return render(<Harness />);
}

describe("SqlConsoleWorkspace", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(executeSql).mockReset();
    vi.mocked(executeSql).mockResolvedValue({
      success: true,
      columns: ["id", "name"],
      rows: [{ id: 1, name: "Ada" }],
      rowCount: 1,
      latencyMs: 7,
      warnings: [],
      notices: [],
      truncated: false,
    });
  });

  it("renders a Monaco-backed SQL editor and disables execute for empty SQL", () => {
    const { container } = renderConsole({ draftSql: "   ", entries: [], running: false });

    const editor = screen.getByTestId("sql-console-editor");
    expect(editor).toBeTruthy();
    expect(editor.closest(".sql-console-scroll")).toBeTruthy();
    expect(container.querySelector(".sql-console-editor-shell")).toBeNull();
    expect(screen.queryByRole("textbox", { name: "SQL 输入" })).toBeNull();
    expect((screen.getByRole("button", { name: /运行/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("executes the current SQL once and renders result metadata", async () => {
    renderConsole({ draftSql: "SELECT 1 AS id, 'Ada' AS name", entries: [], running: false });

    fireEvent.click(screen.getByRole("button", { name: /运行/ }));

    await waitFor(() => {
      expect(executeSql).toHaveBeenCalledTimes(1);
      expect(executeSql).toHaveBeenCalledWith("ds-1", "SELECT 1 AS id, 'Ada' AS name", "SQL Console");
    });
    expect(await screen.findByText(/1 行 · 7ms/)).toBeTruthy();
    expect(screen.getByText("Ada")).toBeTruthy();
  });

  it("executes selected SQL without clearing the full editor draft", async () => {
    renderConsole({
      draftSql: "SELECT * FROM orders;\nSELECT selected_id FROM orders;",
      entries: [],
      running: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "mock-run-selection" }));

    await waitFor(() => {
      expect(executeSql).toHaveBeenCalledWith("ds-1", "SELECT selected_id FROM orders", "SQL Console");
    });
    expect((screen.getByTestId("sql-console-editor") as HTMLTextAreaElement).value).toContain("SELECT * FROM orders");
  });

  it("locks editor actions while a query is running", () => {
    renderConsole({ draftSql: "SELECT 1", entries: [], running: true });

    expect((screen.getByTestId("sql-console-editor") as HTMLTextAreaElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /运行中/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});
