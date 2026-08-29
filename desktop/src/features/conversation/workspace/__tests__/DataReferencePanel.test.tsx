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
      type: "dbfox.data.sql",
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
      id: "result-view-1",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "dbfox.data.result_view",
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

  it("uses a CSP-safe native disclosure for derived data references", () => {
    const { container } = render(<DataReferencePanel artifacts={artifacts()} />);

    expect(screen.getByText("引用的数据来源")).toBeTruthy();
    const disclosure = container.querySelector("details");
    const trigger = container.querySelector("summary");
    expect(disclosure).toBeTruthy();
    expect(trigger).toBeTruthy();
    expect(disclosure?.open).toBe(false);
    expect(container.querySelector("[style]")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();

    fireEvent.click(trigger!);
    expect(disclosure?.open).toBe(true);
    expect(screen.queryByText("SQL: 趋势分析")).toBeNull();
    expect(screen.getByText("分页结果")).toBeTruthy();
    expect(screen.queryByText("orders.amount")).toBeNull();
  });

  it("labels uncited artifacts as saved results rather than evidence", () => {
    render(<DataReferencePanel artifacts={artifacts()} kind="saved" />);

    expect(screen.getByText("已保存结果")).toBeTruthy();
    expect(screen.queryByText("引用的数据来源")).toBeNull();
  });

  it("selects artifact references for the dock when a selector is provided", () => {
    const onSelectArtifact = vi.fn();
    const { container } = render(
      <DataReferencePanel
        artifacts={artifacts()}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    fireEvent.click(container.querySelector("summary")!);
    fireEvent.click(screen.getByText("分页结果"));
    expect(onSelectArtifact).toHaveBeenCalledWith("result-view-1");

  });
});
