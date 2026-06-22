import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
        used_tables: ["orders"],
      },
      depends_on: [],
    },
    {
      id: "result-1",
      conversation_id: "conv",
      run_id: "run",
      type: "table",
      title: "结果表",
      status: "completed",
      payload: {
        columns: ["day", "gmv"],
        rows: [{ day: "2026-06-01", gmv: 120 }],
        rowCount: 1,
      },
      depends_on: ["sql-1"],
    },
    {
      id: "chart-1",
      conversation_id: "conv",
      run_id: "run",
      type: "chart",
      title: "趋势图",
      status: "completed",
      payload: {
        type: "bar",
        source_refs: [
          { label: "GMV", formula: "SUM(orders.amount)", field: "orders.amount" },
        ],
      },
      depends_on: ["result-1"],
    },
    {
      id: "result-view-1",
      conversation_id: "conv",
      run_id: "run",
      type: "result_view",
      title: "分页结果",
      status: "completed",
      payload: {
        columns: ["day", "gmv"],
        previewRows: [{ day: "2026-06-01", gmv: 120 }],
        rowCount: 128,
      },
      depends_on: ["sql_candidate"],
    },
  ];
}

describe("DataReferencePanel", () => {
  it("derives clickable data reference chips from artifacts", () => {
    const onOpenSqlConsole = vi.fn();
    render(<DataReferencePanel artifacts={artifacts()} onOpenSqlConsole={onOpenSqlConsole} />);

    expect(screen.getByText("数据来源")).toBeTruthy();
    expect(screen.getByText("orders")).toBeTruthy();
    expect(screen.getByText("orders.amount")).toBeTruthy();
    expect(screen.getByText("SQL: 趋势分析")).toBeTruthy();
    expect(screen.getByText("结果表")).toBeTruthy();
    expect(screen.getByText("分页结果")).toBeTruthy();
    expect(screen.getByText("趋势图")).toBeTruthy();

    fireEvent.click(screen.getByText("SQL: 趋势分析"));
    expect(onOpenSqlConsole).toHaveBeenCalledWith("SELECT SUM(amount) AS gmv FROM orders GROUP BY DATE(created_at)");
  });
});
