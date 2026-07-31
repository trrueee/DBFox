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

  it("keeps unsupported artifacts opaque instead of exposing their payload", () => {
    const artifact = {
      id: "future-1",
      type: "future_artifact",
      title: "未来工件",
      secretPayload: "must-not-render",
    } as unknown as AgentArtifact;

    render(
      <ArtifactRenderer
        artifacts={[artifact]}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
        onToast={vi.fn()}
      />,
    );

    expect(screen.getByText("未来工件")).toBeTruthy();
    expect(screen.getByText("此工件的引用已安全保留，当前版本暂不支持直接预览。")).toBeTruthy();
    expect(screen.queryByText(/must-not-render/)).toBeNull();
  });
});
