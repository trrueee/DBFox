import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { ArtifactEvidencePanel } from "../ArtifactEvidencePanel";

describe("ArtifactEvidencePanel", () => {
  it("groups SQL, table, and chart by depends_on", () => {
    const artifacts: ConversationArtifact[] = [
      {
        id: "sql-1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "sql",
        title: "SQL 1",
        status: "completed",
        sequence: 1,
        payload: { sql: "select 1" },
        depends_on: [],
      },
      {
        id: "table-1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "table",
        title: "Rows",
        status: "completed",
        sequence: 2,
        payload: { columns: ["value"], rows: [{ value: 1 }] },
        depends_on: ["sql-1"],
      },
      {
        id: "chart-1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "chart",
        title: "Chart",
        status: "completed",
        sequence: 3,
        payload: { type: "bar", series: [{ label: "A", value: 1 }] },
        depends_on: ["table-1"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("SQL 1")).toBeTruthy();
    expect(screen.getByText("Rows")).toBeTruthy();
    expect(screen.getByText("Chart")).toBeTruthy();
  });

  it("renders sql_suggestion, table preview, and chart values from agent artifacts", () => {
    const artifacts: ConversationArtifact[] = [
      {
        id: "sql_suggestion_1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "sql_suggestion",
        title: "SQL candidate",
        status: "completed",
        sequence: 1,
        payload: { safe_sql: "SELECT user_type, COUNT(*) AS user_count FROM id_users GROUP BY user_type" },
        depends_on: [],
      },
      {
        id: "result_table_1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "table",
        title: "Query result",
        status: "completed",
        sequence: 2,
        payload: {
          columns: ["user_type", "user_count"],
          rows: [{ user_type: "personal_user", user_count: 25 }],
        },
        depends_on: ["sql_suggestion_1"],
      },
      {
        id: "chart_suggestion_1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "chart",
        title: "user_count by user_type",
        status: "completed",
        sequence: 3,
        payload: {
          type: "bar",
          series: [{ label: "personal_user", value: 25 }],
        },
        depends_on: ["result_table_1"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("SQL candidate")).toBeTruthy();
    expect(screen.getByText("Query result")).toBeTruthy();
    expect(screen.getByText("user_type")).toBeTruthy();
    expect(screen.getAllByText("personal_user").length).toBeGreaterThan(0);
    expect(screen.getByText("user_count by user_type")).toBeTruthy();
    expect(screen.getAllByText("25").length).toBeGreaterThan(0);
  });

  it("renders different chart previews for bar, line, and pie suggestions", () => {
    const base = {
      conversation_id: "conv",
      run_id: "run",
      message_id: "assistant",
      status: "completed" as const,
      sequence: 1,
      depends_on: [],
    };
    const artifacts: ConversationArtifact[] = [
      {
        ...base,
        id: "bar-chart",
        type: "chart",
        title: "Bar chart",
        payload: { type: "bar", series: [{ label: "A", value: 10 }] },
      },
      {
        ...base,
        id: "line-chart",
        type: "chart",
        title: "Line chart",
        payload: { type: "line", series: [{ label: "Jan", value: 8 }, { label: "Feb", value: 14 }] },
      },
      {
        ...base,
        id: "pie-chart",
        type: "chart",
        title: "Pie chart",
        payload: { type: "pie", series: [{ label: "personal_user", value: 25 }, { label: "enterprise", value: 5 }] },
      },
    ];

    const { container } = render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(container.querySelector(".conv-chart-preview-bar")).toBeTruthy();
    expect(container.querySelector(".conv-chart-preview-line")).toBeTruthy();
    expect(container.querySelector(".conv-chart-preview-pie")).toBeTruthy();
  });
});
