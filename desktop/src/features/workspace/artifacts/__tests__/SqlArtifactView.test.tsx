import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SqlArtifact } from "../../../../types/agentArtifact";
import { SqlArtifactView } from "../SqlArtifactView";

function makeSqlArtifact(): SqlArtifact {
  return {
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
}

describe("SqlArtifactView", () => {
  beforeEach(() => cleanup());

  it("renders SQL metadata chips", () => {
    const artifact = makeSqlArtifact();

    const { container } = render(<SqlArtifactView artifact={artifact} onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);
    const meta = container.querySelector(".artifact-card-meta");

    expect(screen.getByText("分析查询")).toBeTruthy();
    expect(meta?.textContent).toContain("orders");
    expect(screen.getByText("校验 passed")).toBeTruthy();
    expect(screen.getByText("执行 completed")).toBeTruthy();
    expect(screen.getByText("12 行")).toBeTruthy();
    expect(screen.getByText("42ms")).toBeTruthy();
  });

  it("renders SQL in a synchronous highlighted preview instead of Monaco", () => {
    const { container } = render(<SqlArtifactView artifact={makeSqlArtifact()} onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);

    expect(screen.queryByText("Loading...")).toBeNull();
    expect(container.querySelector(".sql-code-block")).toBeTruthy();
    expect(container.querySelector(".sql-token-keyword")?.textContent).toBe("SELECT");
    expect(container.querySelector(".sql-token-function")?.textContent).toBe("SUM");
  });
});
