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
});
