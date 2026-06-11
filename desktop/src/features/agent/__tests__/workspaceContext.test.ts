import { describe, expect, it } from "vitest";
import type { DataSource, Project, QueryResult } from "../../../lib/api";
import { buildAgentWorkspaceContext, extractEditorAnnotations } from "../workspaceContext";

const datasource: DataSource = {
  id: "ds-1",
  project_id: "project-1",
  name: "Demo",
  db_type: "mysql",
  host: "localhost",
  port: 3306,
  database_name: "/tmp/test_engine.db",
  username: "test",
  connection_mode: "direct",
  status: "active",
  created_at: "2026-06-02T00:00:00Z",
};

const project: Project = {
  id: "project-1",
  name: "Demo Project",
  description: "",
  status: "active",
  datasource_count: 1,
  created_at: "2026-06-02T00:00:00Z",
  updated_at: "2026-06-02T00:00:00Z",
};

describe("buildAgentWorkspaceContext", () => {
  it("includes datasource id, active sql, last result, and selected table", () => {
    const result: QueryResult = {
      success: true,
      columns: ["id", "username"],
      rows: [{ id: 1, username: "alice" }],
      rowCount: 1,
      latencyMs: 12,
      guardrail: { result: "pass", originalSql: "", safeSql: "", checks: [], message: "" },
      historyId: "history-1",
    };

    const context = buildAgentWorkspaceContext({
      currentProject: project,
      currentDatasource: datasource,
      activeSql: "SELECT id, username FROM users LIMIT 10",
      lastQueryResult: result,
      selectedTable: { id: "tbl-users", table_name: "users", table_comment: "", table_type: "BASE TABLE", row_count_estimate: 1, columns_count: 2 },
      openSqlTabs: [{ id: "query-1", title: "Query", type: "query", sqlDraft: "SELECT id FROM users" }],
    });

    expect(context?.datasource_id).toBe("ds-1");
    expect(context?.project_id).toBe("project-1");
    expect(context?.active_sql).toContain("SELECT id");
    expect(context?.last_query_result_preview?.rowCount).toBe(1);
    expect(context?.selected_table_names).toEqual(["users"]);
    expect(context?.open_sql_tabs?.[0].sql).toContain("SELECT id");
  });

  it("returns null without a datasource and does not crash", () => {
    expect(buildAgentWorkspaceContext({ currentDatasource: null })).toBeNull();
  });

  it("extracts editor annotations separately from sql", () => {
    expect(extractEditorAnnotations("SELECT id FROM users\n@chart bar")).toEqual([
      { line: 2, text: "@chart bar" },
    ]);
  });
});
