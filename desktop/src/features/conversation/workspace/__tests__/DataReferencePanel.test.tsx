import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { DataReferencePanel } from "../DataReferencePanel";

function artifacts(): ConversationArtifact[] {
  return [
    {
      id: "sql-1",
      conversation_id: "conv",
      run_id: "run",
      type: "sql",
      title: "趋势分析",
      status: "completed",
      payload: {
        sql: "SELECT SUM(amount) AS gmv FROM orders GROUP BY DATE(created_at)",
        usedTables: ["orders"],
      },
      depends_on: [],
    },
    {
      id: "chart-1",
      conversation_id: "conv",
      run_id: "run",
      type: "chart",
      title: "趋势图",
      status: "completed",
      payload: {
        chartType: "bar",
        sourceResultArtifactId: "result-view-1",
        sourceRefs: [
          { label: "GMV", formula: "SUM(orders.amount)", field: "orders.amount" },
        ],
      },
      depends_on: ["result-view-1"],
    },
    {
      id: "result-view-1",
      conversation_id: "conv",
      run_id: "run",
      type: "result_view",
      title: "分页结果",
      status: "completed",
      payload: {
        sourceSqlArtifactId: "sql-1",
        queryFingerprint: "query-gmv",
        datasourceGeneration: 1,
        columns: ["day", "gmv"],
        rowCount: 128,
        returnedRows: 50,
        latencyMs: 4,
        executedAt: "2026-07-19T00:00:00Z",
        truncated: true,
      },
      depends_on: ["sql_candidate"],
    },
  ];
}

describe("DataReferencePanel", () => {
  beforeEach(() => {
    cleanup();
  });

  it("derives clickable data reference chips from artifacts", () => {
    const onOpenSqlConsole = vi.fn();
    render(<DataReferencePanel artifacts={artifacts()} onOpenSqlConsole={onOpenSqlConsole} />);

    expect(screen.getByText("数据来源")).toBeTruthy();
    expect(screen.getByText("orders")).toBeTruthy();
    expect(screen.getByText("orders.amount")).toBeTruthy();
    expect(screen.getByText("SQL: 趋势分析")).toBeTruthy();
    expect(screen.getByText("分页结果")).toBeTruthy();
    expect(screen.getByText("趋势图")).toBeTruthy();

    fireEvent.click(screen.getByText("SQL: 趋势分析"));
    expect(onOpenSqlConsole).toHaveBeenCalledWith("SELECT SUM(amount) AS gmv FROM orders GROUP BY DATE(created_at)");
  });

  it("selects artifact references for the dock when a selector is provided", () => {
    const onOpenSqlConsole = vi.fn();
    const onSelectArtifact = vi.fn();
    render(
      <DataReferencePanel
        artifacts={artifacts()}
        onOpenSqlConsole={onOpenSqlConsole}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    fireEvent.click(screen.getByText("SQL: 趋势分析"));
    expect(onSelectArtifact).toHaveBeenCalledWith("sql-1");
    expect(onOpenSqlConsole).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("分页结果"));
    expect(onSelectArtifact).toHaveBeenCalledWith("result-view-1");

    fireEvent.click(screen.getByText("趋势图"));
    expect(onSelectArtifact).toHaveBeenCalledWith("chart-1");
  });
});
