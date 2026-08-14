import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { DataReferencePanel } from "../DataReferencePanel";

function artifacts(): ConversationArtifact[] {
  return [
    {
      id: "sql-1",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "sql",
      visibility: "supporting",
      title: "趋势分析",
      status: "completed",
      payload: {
        sql: "SELECT SUM(amount) AS gmv FROM orders GROUP BY DATE(created_at)",
        safeSql: "SELECT SUM(amount) AS gmv FROM orders GROUP BY DATE(created_at)",
        dialect: "sqlite",
        queryFingerprint: "query-gmv",
      },
      provenance: {},
      relations: [],
    },
    {
      id: "chart-1",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "chart",
      visibility: "primary",
      title: "趋势图",
      status: "completed",
      payload: {
        chartType: "bar",
        sourceResultArtifactId: "result-view-1",
        x: "day",
        y: ["gmv"],
        aggregation: "sum",
        title: "趋势图",
      },
      provenance: {},
      relations: [{ relation: "visualized_as", artifact_id: "result-view-1" }],
    },
    {
      id: "result-view-1",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "result_view",
      visibility: "primary",
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
      provenance: {},
      relations: [{ relation: "executed_as", artifact_id: "sql-1" }],
    },
  ];
}

describe("DataReferencePanel", () => {
  beforeEach(() => {
    cleanup();
  });

  it("derives clickable data reference chips from artifacts", () => {
    render(<DataReferencePanel artifacts={artifacts()} />);

    expect(screen.getByText("引用的数据来源")).toBeTruthy();
    expect(screen.queryByText("SQL: 趋势分析")).toBeNull();
    expect(screen.getByText("分页结果")).toBeTruthy();
    expect(screen.getByText("趋势图")).toBeTruthy();
    expect(screen.queryByText("orders.amount")).toBeNull();
  });

  it("labels uncited artifacts as saved results rather than evidence", () => {
    render(<DataReferencePanel artifacts={artifacts()} kind="saved" />);

    expect(screen.getByText("已保存结果")).toBeTruthy();
    expect(screen.queryByText("引用的数据来源")).toBeNull();
  });

  it("selects artifact references for the dock when a selector is provided", () => {
    const onSelectArtifact = vi.fn();
    render(
      <DataReferencePanel
        artifacts={artifacts()}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    fireEvent.click(screen.getByText("分页结果"));
    expect(onSelectArtifact).toHaveBeenCalledWith("result-view-1");

    fireEvent.click(screen.getByText("趋势图"));
    expect(onSelectArtifact).toHaveBeenCalledWith("chart-1");
  });
});
