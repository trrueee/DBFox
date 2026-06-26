import type { CSSProperties } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { ArtifactEvidencePanel } from "../ArtifactEvidencePanel";

const echartsMock = vi.hoisted(() => ({
  options: [] as unknown[],
}));

vi.mock("echarts-for-react", () => ({
  default: ({ option, style }: { option: unknown; style?: CSSProperties }) => {
    echartsMock.options.push(option);
    return <div data-testid="echarts-mock" style={style} />;
  },
}));

describe("ArtifactEvidencePanel", () => {
  beforeEach(() => {
    cleanup();
    echartsMock.options = [];
  });

  it("groups SQL, result view, and chart by depends_on", () => {
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
        id: "result-view-1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "result_view",
        title: "Rows",
        status: "completed",
        sequence: 2,
        payload: {
          storageMode: "sql_backed",
          datasourceId: "ds-1",
          sourceSqlArtifactId: "sql-1",
          safeSql: "select 1",
          columns: ["value"],
          previewRows: [{ value: 1 }],
          rowCount: 1,
        },
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
        depends_on: ["result-view-1"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("SQL 1")).toBeTruthy();
    expect(screen.getByText("Rows")).toBeTruthy();
    expect(screen.getByText("Chart")).toBeTruthy();
  });

  it("renders sql_suggestion, result view preview, and chart values from agent artifacts", () => {
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
        id: "result_view_1",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "result_view",
        title: "Query result",
        status: "completed",
        sequence: 2,
        payload: {
          storageMode: "sql_backed",
          datasourceId: "ds-1",
          sourceSqlArtifactId: "sql_suggestion_1",
          safeSql: "SELECT user_type, COUNT(*) AS user_count FROM id_users GROUP BY user_type",
          columns: ["user_type", "user_count"],
          previewRows: [{ user_type: "personal_user", user_count: 25 }],
          rowCount: 1,
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
        depends_on: ["result_view_1"],
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

  it("renders chart artifacts through compact ChartArtifactView", () => {
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
      {
        ...base,
        id: "scatter-chart",
        type: "chart",
        title: "Scatter chart",
        payload: { chart_type: "scatter", series: [{ label: "10", value: 25 }, { label: "20", value: 55 }] },
      },
    ];

    const { container } = render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(container.querySelectorAll(".chart-artifact-card.is-compact")).toHaveLength(4);
    expect(
      echartsMock.options.map((option) => (
        option as { series: Array<{ type: string }> }
      ).series[0].type),
    ).toEqual(["bar", "line", "pie", "scatter"]);
  });

  it("renders result view previews with row counts and a 10-row limit", () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({
      day: `2026-06-${String(index + 1).padStart(2, "0")}`,
      order_count: (index + 1) * 10,
    }));
    const artifacts: ConversationArtifact[] = [
      {
        id: "result-view-preview",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "result_view",
        title: "Daily orders",
        status: "completed",
        sequence: 1,
        payload: {
          storageMode: "sql_backed",
          datasourceId: "ds-1",
          sourceSqlArtifactId: "sql-artifact",
          safeSql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
          columns: ["day", "order_count"],
          previewRows: rows,
          rowCount: 128,
          returnedRows: 12,
          latencyMs: 42,
          truncated: true,
        },
        depends_on: [],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("预览 10 / 共 128 行")).toBeTruthy();
    expect(screen.getByText("2 列")).toBeTruthy();
    expect(screen.getByText("42ms")).toBeTruthy();
    expect(screen.getByText("结果已截断")).toBeTruthy();
    expect(screen.getByText("2026-06-10")).toBeTruthy();
    expect(screen.queryByText("2026-06-11")).toBeNull();
  });

  it("opens a result view preview as a SQL-backed result tab", () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({
      day: `2026-06-${String(index + 1).padStart(2, "0")}`,
      order_count: (index + 1) * 10,
    }));
    const onOpenResultTab = vi.fn();
    const artifacts: ConversationArtifact[] = [
      {
        id: "result-view-preview",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "result_view",
        title: "Daily orders",
        status: "completed",
        sequence: 1,
        payload: {
          storageMode: "sql_backed",
          datasourceId: "ds-1",
          sourceSqlArtifactId: "sql-artifact",
          sourceSql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
          safeSql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
          columns: ["day", "order_count"],
          previewRows: rows,
          rowCount: 128,
          returnedRows: 12,
        },
        depends_on: [],
      },
    ];

    render(
      <ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} onOpenResultTab={onOpenResultTab} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "打开为 Tab" }));

    expect(onOpenResultTab).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "result-view-preview",
        type: "result_view",
        title: "Daily orders",
        storageMode: "sql_backed",
        datasourceId: "ds-1",
        sourceSqlSemanticId: "sql-artifact",
        safeSql: "SELECT day, COUNT(*) AS order_count FROM orders GROUP BY day",
        columns: ["day", "order_count"],
        rowCount: 128,
        returnedRows: 12,
      }),
    );
    expect(onOpenResultTab.mock.calls[0][0].previewRows).toHaveLength(12);
  });

  it("groups SQL, safety, result_view, and chart by semantic ids", () => {
    const artifacts: ConversationArtifact[] = [
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
        title: "Result view",
        status: "completed",
        sequence: 3,
        payload: {
          columns: ["id", "amount"],
          previewRows: [{ id: 1, amount: 20 }],
          rowCount: 1,
          storageMode: "sql_backed",
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

    const { container } = render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    const group = container.querySelector(".conv-sql-group");
    expect(group).toBeTruthy();
    expect(group?.textContent).toContain("SQL");
    expect(group?.textContent).toContain("安全检查");
    expect(group?.textContent).toContain("Result view");
    expect(group?.textContent).toContain("Amount chart");
  });

  it("keeps ungrouped safety artifacts visible", () => {
    const artifacts: ConversationArtifact[] = [
      {
        id: "orphan-safety",
        semantic_id: "safety_orphan",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "safety",
        title: "Safety",
        status: "completed",
        sequence: 1,
        payload: {
          passed: false,
          can_execute: false,
          requires_confirmation: true,
          guardrail_result: "blocked",
          schema_warnings_count: 2,
        },
        depends_on: ["missing_sql"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("安全检查")).toBeTruthy();
    expect(screen.getByText("不可执行")).toBeTruthy();
    expect(screen.getByText("需要确认")).toBeTruthy();
  });

  it("shows redaction audit details on safety artifacts", () => {
    const artifacts: ConversationArtifact[] = [
      {
        id: "sql-redaction",
        semantic_id: "sql_candidate",
        conversation_id: "conv",
        run_id: "run",
        message_id: "assistant",
        type: "sql",
        title: "SQL",
        status: "completed",
        sequence: 1,
        payload: { sql: "SELECT name, phone, email FROM users" },
        depends_on: [],
      },
      {
        id: "safety-redaction",
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
          guardrail_result: "pass",
          redaction: {
            redacted_count: 3,
            fields: ["users.name", "users.phone", "users.email"],
          },
        },
        depends_on: ["sql_candidate"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("已脱敏 3 个字段")).toBeTruthy();
    expect(screen.getByText("users.name, users.phone, users.email")).toBeTruthy();
  });
});
