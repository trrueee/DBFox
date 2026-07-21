import { describe, expect, it } from "vitest";
import type { AgentArtifact } from "../../../lib/api";
import { toViewArtifacts } from "../artifactProjection";

describe("artifactProjection", () => {
  it("maps SQL, result view, and chart metadata for artifact views", () => {
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
          usedTables: ["orders"],
          validationStatus: "passed",
          executionStatus: "completed",
          rowCount: 12,
          latencyMs: 42,
        },
        depends_on: [],
        refs: [],
      },
      {
        id: "result-view-1",
        semantic_id: "result_view_gmv",
        type: "result_view",
        title: "Result view",
        status: "completed",
        presentation: { mode: "both", priority: 1, collapsed: false },
        payload: {
          sourceSqlArtifactId: "sql-1",
          queryFingerprint: "query-gmv",
          datasourceGeneration: 1,
          columns: ["gmv"],
          rowCount: 12,
          returnedRows: 1,
          latencyMs: 42,
          executedAt: "2026-07-19T00:00:00Z",
          truncated: false,
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
          chartType: "bar",
          sourceResultArtifactId: "result-view-1",
          x: "day",
          y: ["gmv"],
          aggregation: "sum",
          title: "GMV chart",
        },
        depends_on: ["result-view-1"],
        refs: [],
      },
    ];

    const viewArtifacts = toViewArtifacts(artifacts);
    const sql = viewArtifacts.find((artifact) => artifact.type === "sql");
    const resultView = viewArtifacts.find((artifact) => artifact.type === "result_view");
    const chart = viewArtifacts.find((artifact) => artifact.type === "chart");

    expect(sql?.type).toBe("sql");
    if (sql?.type !== "sql") throw new Error("Expected SQL artifact");
    expect(sql.purpose).toBe("分析查询");
    expect(sql.usedTables).toEqual(["orders"]);
    expect(sql.rowCount).toBe(12);
    expect(sql.latencyMs).toBe(42);

    expect(resultView?.type).toBe("result_view");
    if (resultView?.type !== "result_view") throw new Error("Expected result_view artifact");
    expect(resultView.queryFingerprint).toBe("query-gmv");
    expect(resultView).not.toHaveProperty("safeSql");

    expect(chart?.type).toBe("chart");
    if (chart?.type !== "chart") throw new Error("Expected chart artifact");
    expect(chart.x).toBe("day");
    expect(chart.y).toEqual(["gmv"]);
  });

  it("does not render chart artifacts without a source result reference", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "chart-1",
        semantic_id: "chart",
        type: "chart",
        title: "GMV chart",
        status: "completed",
        presentation: { mode: "inline", priority: 1, collapsed: false },
        payload: {
          chartType: "bar",
          x: "day",
          y: ["gmv"],
        },
        depends_on: ["result-view-1"],
        refs: [],
      },
    ];

    expect(toViewArtifacts(artifacts)).toEqual([]);
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
          sourceSqlArtifactId: "artifact-sql-1",
          queryFingerprint: "query-orders",
          datasourceGeneration: 1,
          columns: ["id", "amount"],
          rowCount: 128,
          returnedRows: 1,
          latencyMs: 42,
          executedAt: "2026-07-19T00:00:00Z",
          truncated: true,
        },
        depends_on: ["sql_candidate"],
        refs: [],
      },
    ];

    const [resultView] = toViewArtifacts(artifacts);

    expect(resultView?.type).toBe("result_view");
    if (resultView?.type !== "result_view") throw new Error("Expected result_view artifact");
    expect(resultView.sourceSqlArtifactId).toBe("artifact-sql-1");
    expect(resultView.queryFingerprint).toBe("query-orders");
    expect(resultView.columns).toEqual(["id", "amount"]);
    expect(resultView).not.toHaveProperty("previewRows");
    expect(resultView.rowCount).toBe(128);
    expect(resultView.depends_on).toEqual(["sql_candidate"]);
  });

  it("preserves backend pie and scatter chart types with metadata", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "pie-chart",
        semantic_id: "chart_pie",
        type: "chart",
        title: "GMV share",
        status: "completed",
        presentation: { mode: "inline", priority: 1, collapsed: false },
        payload: {
          chartType: "pie",
          sourceResultArtifactId: "result-pie",
          x: "user_type",
          y: ["gmv"],
          aggregation: "sum",
          title: "GMV share",
        },
        depends_on: ["result_view"],
        refs: [],
      },
      {
        id: "scatter-chart",
        semantic_id: "chart_scatter",
        type: "chart",
        title: "Order scatter",
        status: "completed",
        presentation: { mode: "inline", priority: 2, collapsed: false },
        payload: {
          chartType: "scatter",
          sourceResultArtifactId: "result-scatter",
          x: "order_count",
          y: ["gmv"],
          aggregation: "none",
          title: "Order scatter",
        },
        depends_on: ["result_view"],
        refs: [],
      },
    ];

    const charts = toViewArtifacts(artifacts).filter((artifact) => artifact.type === "chart");

    expect(charts).toHaveLength(2);
    expect(charts.map((chart) => chart.chartType)).toEqual(["pie", "scatter"]);
    expect(charts[0].type === "chart" ? charts[0].aggregation : undefined).toBe("sum");
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
          canExecute: true,
          requiresApproval: false,
          guardrailResult: "passed",
          schemaWarningsCount: 0,
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
          canExecute: true,
          requiresApproval: false,
          guardrail: { result: "passed" },
          schemaWarnings: ["ambiguous column"],
          redaction: {
            redactedCount: 2,
            fields: ["users.phone", "users.email"],
          },
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
    expect(safety.content).toContain("已脱敏 2 个字段");
    expect(safety.content).toContain("users.phone, users.email");
  });
});
