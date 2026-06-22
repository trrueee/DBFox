import type { CSSProperties } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { ArtifactDock } from "../ArtifactDock";

const echartsMock = vi.hoisted(() => ({
  options: [] as unknown[],
}));

vi.mock("echarts-for-react", () => ({
  default: ({ option, style }: { option: unknown; style?: CSSProperties }) => {
    echartsMock.options.push(option);
    return <div data-testid="echarts-mock" style={style} />;
  },
}));

function trustedQueryArtifacts(): ConversationArtifact[] {
  return [
    {
      id: "artifact-sql",
      semantic_id: "sql_candidate",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "sql",
      title: "SQL",
      status: "completed",
      sequence: 1,
      payload: { sql: "SELECT id, amount FROM orders" },
      depends_on: [],
    },
    {
      id: "artifact-safety",
      semantic_id: "safety_report",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "safety",
      title: "Safety",
      status: "completed",
      sequence: 2,
      payload: {
        passed: true,
        can_execute: true,
        requires_confirmation: false,
        guardrail_result: "passed",
        schema_warnings_count: 0,
      },
      depends_on: ["sql_candidate"],
    },
    {
      id: "artifact-result",
      semantic_id: "result_view_1",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "result_view",
      title: "Order result",
      status: "completed",
      sequence: 3,
      payload: {
        columns: ["id", "amount"],
        previewRows: [{ id: 1, amount: 20 }],
        rowCount: 1,
        storageMode: "payload",
        safeSql: "SELECT id, amount FROM orders",
      },
      depends_on: ["sql_candidate"],
    },
    {
      id: "artifact-chart",
      semantic_id: "chart_1",
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      type: "chart",
      title: "Amount chart",
      status: "completed",
      sequence: 4,
      payload: { type: "bar", series: [{ label: "1", value: 20 }] },
      depends_on: ["result_view_1"],
    },
  ];
}

describe("ArtifactDock", () => {
  beforeEach(() => {
    cleanup();
    echartsMock.options = [];
  });

  it("opens on the query result by default and keeps SQL, safety, result, and chart selectable", () => {
    const onSelectArtifact = vi.fn();
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    expect(screen.getByRole("complementary", { name: "Artifact dock" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "SQL SQL" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Safety Safety" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Order result Result" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Amount chart Chart" })).toBeTruthy();
    expect(screen.getByText("预览 1 / 共 1 行")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "SQL SQL" }));

    expect(onSelectArtifact).toHaveBeenCalledWith("artifact-sql");
    expect(screen.getByText("SELECT id, amount FROM orders")).toBeTruthy();
  });

  it("honors a selected artifact id from the conversation evidence chip", () => {
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        selectedArtifactId="artifact-safety"
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Safety Safety" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("安全检查")).toBeTruthy();
    expect(screen.getByText("Guardrail: passed")).toBeTruthy();
  });
});
