import type { CSSProperties } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { agentApi } from "../../../../lib/api/agent";
import { ArtifactEvidencePanel } from "../ArtifactEvidencePanel";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    fetchArtifactChartData: vi.fn(),
  },
}));

const LAZY_CHART_TIMEOUT_MS = 10_000;

async function findLazyChartText(text: string) {
  await vi.dynamicImportSettled();
  return screen.findByText(text, {}, { timeout: LAZY_CHART_TIMEOUT_MS });
}

const echartsMock = vi.hoisted(() => ({
  options: [] as unknown[],
}));

vi.mock("echarts-for-react/lib/core", () => ({
  default: ({ option, style }: { option: unknown; style?: CSSProperties }) => {
    echartsMock.options.push(option);
    return <div data-testid="echarts-mock" style={style} />;
  },
}));

describe("ArtifactEvidencePanel", () => {
  beforeEach(() => {
    cleanup();
    echartsMock.options = [];
    vi.mocked(agentApi.fetchArtifactChartData).mockReset();
    vi.mocked(agentApi.fetchArtifactChartData).mockResolvedValue({
      series: [{ label: "A", value: 1 }], sampleSize: 1, truncated: false,
      consistency: "live_reexecution", originalExecutedAt: "2026-07-20T00:00:00Z",
      viewExecutedAt: "2026-07-20T00:00:01Z", viewExecutionId: "view-evidence",
      datasourceGeneration: 1, queryFingerprint: "query-evidence",
    });
  });

  it("groups SQL, result view, and chart by depends_on", async () => {
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
          sourceSqlArtifactId: "sql-1",
          queryFingerprint: "query-1",
          columns: ["value"],
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
        payload: { chartType: "bar", sourceResultArtifactId: "result-view-1", x: "value", y: "value" },
        depends_on: ["result-view-1"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    await findLazyChartText("Chart");
    expect(screen.getByText("SQL 1")).toBeTruthy();
    expect(screen.getByText("Rows")).toBeTruthy();
    expect(screen.getByText("Chart")).toBeTruthy();
  });

  it("renders SQL, result descriptor, and chart without persisted result values", async () => {
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
        payload: { safeSql: "SELECT user_type, COUNT(*) AS user_count FROM id_users GROUP BY user_type" },
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
          sourceSqlArtifactId: "sql_suggestion_1",
          queryFingerprint: "query-users",
          columns: ["user_type", "user_count"],
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
          chartType: "bar",
          sourceResultArtifactId: "result_view_1",
          x: "user_type",
          y: "user_count",
        },
        depends_on: ["result_view_1"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    await findLazyChartText("user_count by user_type");
    expect(screen.getByText("SQL candidate")).toBeTruthy();
    expect(screen.getByText("Query result")).toBeTruthy();
    expect(screen.getByText("2 列")).toBeTruthy();
    expect(screen.getByText("打开工件后按需读取数据")).toBeTruthy();
    expect(screen.getByText("user_count by user_type")).toBeTruthy();
  });

  it("renders chart artifacts through compact ChartArtifactView", async () => {
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
        payload: { chartType: "bar", sourceResultArtifactId: "result-1", x: "label", y: "value" },
      },
      {
        ...base,
        id: "line-chart",
        type: "chart",
        title: "Line chart",
        payload: { chartType: "line", sourceResultArtifactId: "result-1", x: "label", y: "value" },
      },
      {
        ...base,
        id: "pie-chart",
        type: "chart",
        title: "Pie chart",
        payload: { chartType: "pie", sourceResultArtifactId: "result-1", x: "label", y: "value" },
      },
      {
        ...base,
        id: "scatter-chart",
        type: "chart",
        title: "Scatter chart",
        payload: { chartType: "scatter", sourceResultArtifactId: "result-1", x: "label", y: "value" },
      },
    ];

    const { container } = render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    await findLazyChartText("Bar chart");
    expect(container.querySelectorAll(".chart-artifact-card.is-compact")).toHaveLength(4);
    expect(
      echartsMock.options.slice(-4).map((option) => (
        option as { series: Array<{ type: string }> }
      ).series[0].type),
    ).toEqual(["bar", "line", "pie", "scatter"]);
  });

  it("renders only result view metadata in conversation evidence", () => {
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
          sourceSqlArtifactId: "sql-artifact",
          queryFingerprint: "query-daily-orders",
          columns: ["day", "order_count"],
          rowCount: 128,
          returnedRows: 12,
          latencyMs: 42,
          truncated: true,
        },
        depends_on: [],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("共 128 行")).toBeTruthy();
    expect(screen.getByText("2 列")).toBeTruthy();
    expect(screen.getByText("42ms")).toBeTruthy();
    expect(screen.getByText("执行结果已截断")).toBeTruthy();
    expect(screen.getByText("打开工件后按需读取数据")).toBeTruthy();
  });

  it("opens a result view preview as a SQL-backed result tab", () => {
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
          sourceSqlArtifactId: "sql-artifact",
          queryFingerprint: "query-daily-orders",
          columns: ["day", "order_count"],
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
        sourceSqlArtifactId: "sql-artifact",
        queryFingerprint: "query-daily-orders",
        columns: ["day", "order_count"],
        rowCount: 128,
        returnedRows: 12,
      }),
    );
    expect(onOpenResultTab.mock.calls[0][0]).not.toHaveProperty("previewRows");
  });

  it("groups SQL, safety, result_view, and chart by semantic ids", async () => {
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
          canExecute: true,
          requiresApproval: false,
          guardrailResult: "passed",
          schemaWarningsCount: 0,
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
          sourceSqlArtifactId: "artifact-sql",
          queryFingerprint: "query-orders",
          columns: ["id", "amount"],
          rowCount: 1,
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
        payload: { chartType: "bar", sourceResultArtifactId: "artifact-result", x: "id", y: "amount" },
        depends_on: ["result_view_1"],
      },
    ];

    const { container } = render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    await findLazyChartText("Amount chart");
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
          canExecute: false,
          requiresApproval: true,
          guardrailResult: "blocked",
          schemaWarningsCount: 2,
        },
        depends_on: ["missing_sql"],
      },
    ];

    render(<ArtifactEvidencePanel artifacts={artifacts} onOpenSqlConsole={vi.fn()} />);

    expect(screen.getByText("安全检查")).toBeTruthy();
    expect(screen.getByText("不可执行")).toBeTruthy();
    expect(screen.getByText("需要批准")).toBeTruthy();
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
          canExecute: true,
          requiresApproval: false,
          guardrailResult: "pass",
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
