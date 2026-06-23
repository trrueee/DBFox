import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SqlArtifact } from "../../../../types/agentArtifact";
import { SqlArtifactView } from "../SqlArtifactView";

vi.mock("@monaco-editor/react", () => ({
  default: ({ value, options }: { value: string; options: { readOnly?: boolean; fontSize?: number } }) => (
    <div data-testid="sql-monaco" data-readonly={String(options.readOnly)} data-font-size={String(options.fontSize)}>
      {value}
    </div>
  ),
}));

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

    render(<SqlArtifactView artifact={artifact} onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);

    expect(screen.getByText("分析查询")).toBeTruthy();
    expect(screen.getByText("orders")).toBeTruthy();
    expect(screen.getByText("校验 passed")).toBeTruthy();
    expect(screen.getByText("执行 completed")).toBeTruthy();
    expect(screen.getByText("12 行")).toBeTruthy();
    expect(screen.getByText("42ms")).toBeTruthy();
  });

  it("renders SQL in a read-only Monaco editor", () => {
    render(<SqlArtifactView artifact={makeSqlArtifact()} onOpenSqlConsole={vi.fn()} onToast={vi.fn()} />);

    const editor = screen.getByTestId("sql-monaco");
    expect(editor.textContent).toContain("SELECT");
    expect(editor.getAttribute("data-readonly")).toBe("true");
    expect(editor.getAttribute("data-font-size")).toBe("12");
  });
});
