import { describe, expect, it } from "vitest";
import type { AgentArtifact } from "../../../lib/api";
import { toViewArtifacts } from "../agentBridge";

describe("agentBridge", () => {
  it("maps array-shaped table rows by column position", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "table-1",
        semantic_id: "result_table",
        type: "table",
        title: "Result table",
        status: "completed",
        presentation: { mode: "both", priority: 1, collapsed: false },
        payload: {
          columns: ["day", "order_count"],
          rows: [["2026-06-01", 12]],
          rowCount: 1,
        },
        depends_on: [],
        refs: [],
      },
    ];

    const [table] = toViewArtifacts(artifacts);

    expect(table?.type).toBe("table");
    if (table?.type !== "table") throw new Error("Expected table artifact");
    expect(table.rows).toEqual([["2026-06-01", "12"]]);
  });

  it("maps SQL, table, and chart metadata for artifact views", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "sql-1",
        semantic_id: "sql_candidate",
        type: "sql",
        title: "Validated SQL",
        status: "completed",
        presentation: { mode: "dock", priority: 1, collapsed: false },
        payload: {
          sql: "SELECT SUM(amount) AS gmv FROM orders",
          purpose: "分析查询",
          used_tables: ["orders"],
          validation_status: "passed",
          execution_status: "completed",
          rowCount: 12,
          latencyMs: 42,
        },
        depends_on: [],
        refs: [],
      },
      {
        id: "table-1",
        semantic_id: "result_table",
        type: "table",
        title: "Result table",
        status: "completed",
        presentation: { mode: "both", priority: 1, collapsed: false },
        payload: {
          columns: ["gmv"],
          rows: [[120]],
          rowCount: 12,
          returnedRows: 1,
          latencyMs: 42,
          notices: ["preview"],
        },
        depends_on: ["sql-1"],
        refs: [],
      },
      {
        id: "chart-1",
        semantic_id: "chart",
        type: "chart",
        title: "GMV chart",
        status: "completed",
        presentation: { mode: "inline", priority: 1, collapsed: false },
        payload: {
          type: "bar",
          x: "day",
          y: "gmv",
          series: [{ label: "2026-06-01", value: 120 }],
          source_refs: [{ label: "GMV", formula: "SUM(orders.amount)", field: "orders.amount" }],
        },
        depends_on: ["table-1"],
        refs: [],
      },
    ];

    const viewArtifacts = toViewArtifacts(artifacts);
    const sql = viewArtifacts.find((artifact) => artifact.type === "sql");
    const table = viewArtifacts.find((artifact) => artifact.type === "table");
    const chart = viewArtifacts.find((artifact) => artifact.type === "chart");

    expect(sql?.type).toBe("sql");
    if (sql?.type !== "sql") throw new Error("Expected SQL artifact");
    expect(sql.purpose).toBe("分析查询");
    expect(sql.usedTables).toEqual(["orders"]);
    expect(sql.rowCount).toBe(12);
    expect(sql.latencyMs).toBe(42);

    expect(table?.type).toBe("table");
    if (table?.type !== "table") throw new Error("Expected table artifact");
    expect(table.notices).toEqual(["preview"]);

    expect(chart?.type).toBe("chart");
    if (chart?.type !== "chart") throw new Error("Expected chart artifact");
    expect(chart.sourceRefs).toEqual([{ label: "GMV", formula: "SUM(orders.amount)", field: "orders.amount" }]);
  });

  it("maps result_view artifacts for sql-backed result tabs", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "result-view-1",
        semantic_id: "result_view_1",
        type: "result_view",
        title: "Result view",
        status: "completed",
        presentation: { mode: "both", priority: 1, collapsed: false },
        payload: {
          storageMode: "sql_backed",
          datasourceId: "ds-1",
          sourceSqlSemanticId: "sql_candidate",
          sourceSql: "SELECT id, amount FROM orders",
          safeSql: "SELECT id, amount FROM orders",
          columns: ["id", "amount"],
          previewRows: [{ id: 1, amount: 20 }],
          previewRowCount: 1,
          rowCount: 128,
          returnedRows: 1,
          latencyMs: 42,
        },
        depends_on: ["sql_candidate"],
        refs: [],
      },
    ];

    const [resultView] = toViewArtifacts(artifacts);

    expect(resultView?.type).toBe("result_view");
    if (resultView?.type !== "result_view") throw new Error("Expected result_view artifact");
    expect(resultView.storageMode).toBe("sql_backed");
    expect(resultView.datasourceId).toBe("ds-1");
    expect(resultView.sourceSqlSemanticId).toBe("sql_candidate");
    expect(resultView.safeSql).toBe("SELECT id, amount FROM orders");
    expect(resultView.columns).toEqual(["id", "amount"]);
    expect(resultView.previewRows).toEqual([["1", "20"]]);
    expect(resultView.rowCount).toBe(128);
    expect(resultView.depends_on).toEqual(["sql_candidate"]);
  });

  it("maps safety artifacts into visible markdown trust summaries", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "safety-1",
        semantic_id: "safety_report",
        type: "safety",
        title: "Safety",
        status: "completed",
        presentation: { mode: "both", priority: 1, collapsed: true },
        payload: {
          passed: true,
          can_execute: true,
          requires_confirmation: false,
          guardrail_result: "passed",
          schema_warnings_count: 0,
        },
        depends_on: ["sql_candidate"],
        refs: [],
      },
    ];

    const [safety] = toViewArtifacts(artifacts);

    expect(safety?.type).toBe("markdown");
    if (safety?.type !== "markdown") throw new Error("Expected markdown artifact");
    expect(safety.title).toBe("安全检查");
    expect(safety.content).toContain("可执行");
    expect(safety.depends_on).toEqual(["sql_candidate"]);
  });

  it("maps nested safety payload details into markdown trust summaries", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "safety-2",
        semantic_id: "safety_report",
        type: "safety",
        title: "Safety",
        status: "completed",
        presentation: { mode: "both", priority: 1, collapsed: true },
        payload: {
          can_execute: true,
          requires_confirmation: false,
          guardrail: { result: "passed" },
          schema_warnings: ["ambiguous column"],
        },
        depends_on: ["sql_candidate"],
        refs: [],
      },
    ];

    const [safety] = toViewArtifacts(artifacts);

    expect(safety?.type).toBe("markdown");
    if (safety?.type !== "markdown") throw new Error("Expected markdown artifact");
    expect(safety.content).toContain("Guardrail：passed");
    expect(safety.content).toContain("Schema warnings：1");
  });
});
