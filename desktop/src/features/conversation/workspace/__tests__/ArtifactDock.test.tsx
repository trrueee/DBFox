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

vi.mock("@monaco-editor/react", () => ({
  default: ({ value }: { value: string }) => <pre data-testid="sql-editor-mock">{value}</pre>,
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

  it("renders as a resizable split pane inside the conversation body", () => {
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    const dock = screen.getByRole("complementary", { name: "Artifact dock" });
    const resizeHandle = screen.getByRole("separator", { name: "调整工件区宽度" });

    expect(dock.style.getPropertyValue("--conv-artifact-width")).toBe("420px");
    expect(resizeHandle.getAttribute("aria-valuemin")).toBe("340");
    expect(resizeHandle.getAttribute("aria-valuemax")).toBe("680");
    expect(resizeHandle.getAttribute("aria-valuenow")).toBe("420");
  });

  it("lets the user drag the artifact split width within desktop bounds", () => {
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    const dock = screen.getByRole("complementary", { name: "Artifact dock" });
    const resizeHandle = screen.getByRole("separator", { name: "调整工件区宽度" });

    fireEvent.pointerDown(resizeHandle, { clientX: 700, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 560, pointerId: 1 });
    fireEvent.pointerUp(window, { pointerId: 1 });

    expect(dock.style.getPropertyValue("--conv-artifact-width")).toBe("560px");

    fireEvent.pointerDown(resizeHandle, { clientX: 560, pointerId: 2 });
    fireEvent.pointerMove(window, { clientX: -200, pointerId: 2 });
    fireEvent.pointerUp(window, { pointerId: 2 });

    expect(dock.style.getPropertyValue("--conv-artifact-width")).toBe("680px");
  });
});
