import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentArtifact } from "../../../../types/agentArtifact";
import { ArtifactRenderer } from "../ArtifactRenderer";

describe("ArtifactRenderer", () => {
  beforeEach(() => cleanup());

  it("renders supported artifact types through the registry", () => {
    const artifacts: AgentArtifact[] = [
      {
        id: "sql-1",
        type: "sql",
        title: "SQL",
        sql: "SELECT id FROM orders",
        purpose: "query",
        validationStatus: "passed",
      },
      {
        id: "markdown-1",
        type: "markdown",
        title: "分析",
        content: "订单上涨。",
      },
    ];

    render(
      <ArtifactRenderer
        artifacts={artifacts}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
        onToast={vi.fn()}
      />,
    );

    expect(screen.getAllByText("SQL").length).toBeGreaterThan(0);
    expect(screen.getAllByText("分析").length).toBeGreaterThan(0);
    expect(screen.getByText("订单上涨。")).toBeTruthy();
  });
});
