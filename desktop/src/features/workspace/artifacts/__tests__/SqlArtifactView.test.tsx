import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SqlArtifact } from "../../../../types/agentArtifact";
import { SqlArtifactView } from "../SqlArtifactView";

describe("SqlArtifactView", () => {
  it("renders SQL metadata chips", () => {
    const artifact: SqlArtifact = {
      id: "sql-1",
      type: "sql",
      title: "执行的 SQL",
      sql: "SELECT SUM(amount) FROM orders",
      purpose: "分析查询",
      usedTables: ["orders"],
      validationStatus: "passed",
      executionStatus: "completed",
      rowCount: 12,
      latencyMs: 42,
    };

    render(<SqlArtifactView artifact={artifact} onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);

    expect(screen.getByText("分析查询")).toBeTruthy();
    expect(screen.getByText("orders")).toBeTruthy();
    expect(screen.getByText("校验 passed")).toBeTruthy();
    expect(screen.getByText("执行 completed")).toBeTruthy();
    expect(screen.getByText("12 行")).toBeTruthy();
    expect(screen.getByText("42ms")).toBeTruthy();
  });
});
