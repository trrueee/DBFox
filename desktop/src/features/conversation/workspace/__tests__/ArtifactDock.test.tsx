import type { CSSProperties } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationArtifact } from "../../../../types/conversation";
import { agentApi } from "../../../../lib/api/agent";
import { ArtifactDock } from "../ArtifactDock";

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: {
    fetchArtifactPage: vi.fn(),
    fetchArtifactChartData: vi.fn(),
    exportArtifactCsv: vi.fn(),
  },
}));

const echartsMock = vi.hoisted(() => ({
  options: [] as unknown[],
}));

vi.mock("echarts-for-react/lib/core", () => ({
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
        canExecute: true,
        requiresApproval: false,
        guardrailResult: "passed",
        schemaWarningsCount: 0,
        safeSql: "SELECT id, amount FROM orders WHERE amount > 10",
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
        sourceSqlArtifactId: "artifact-sql",
        queryFingerprint: "query-1",
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
      payload: { chartType: "bar", sourceResultArtifactId: "artifact-result", x: "id", y: "amount", aggregation: "none" },
      depends_on: ["result_view_1"],
    },
  ];
}

describe("ArtifactDock", () => {
  beforeEach(() => {
    cleanup();
    echartsMock.options = [];
    vi.mocked(agentApi.fetchArtifactPage).mockReset();
    vi.mocked(agentApi.fetchArtifactChartData).mockReset();
    vi.mocked(agentApi.fetchArtifactPage).mockResolvedValue({
      columns: ["id", "amount"], rows: [{ id: 1, amount: 20 }],
      page: 1, pageSize: 10, rowCount: 1, hasNextPage: false,
      latencyMs: 1, consistency: "live_reexecution",
      originalExecutedAt: "2026-07-20T00:00:00Z", viewExecutedAt: "2026-07-20T00:00:01Z",
      viewExecutionId: "view-dock", datasourceGeneration: 1, queryFingerprint: "query-dock",
    });
    vi.mocked(agentApi.fetchArtifactChartData).mockResolvedValue({
      series: [{ label: "1", value: 20 }], sampleSize: 1, truncated: false,
      consistency: "live_reexecution", originalExecutedAt: "2026-07-20T00:00:00Z",
      viewExecutedAt: "2026-07-20T00:00:01Z", viewExecutionId: "view-chart-dock",
      datasourceGeneration: 1, queryFingerprint: "query-chart-dock",
    });
  });

  it("renders the backend-selected result and keeps every related artifact selectable", async () => {
    const onSelectArtifact = vi.fn();
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        selectedArtifactId="artifact-result"
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
    expect(await screen.findByText("本页 1 / 共 1 行")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "SQL SQL" }));

    expect(onSelectArtifact).toHaveBeenCalledWith("artifact-sql");
  });

  it("changes only when the backend selection changes", () => {
    const artifacts = trustedQueryArtifacts();
    const latestSql: ConversationArtifact = {
      ...artifacts[0],
      id: "artifact-sql-latest",
      semantic_id: "sql_candidate_latest",
      run_id: "run-latest",
      title: "Latest SQL",
      sequence: 5,
      payload: { sql: "SELECT COUNT(*) AS count FROM orders" },
    };
    const latestResult: ConversationArtifact = {
      ...artifacts[2],
      id: "artifact-result-latest",
      semantic_id: "result_view_latest",
      run_id: "run-latest",
      title: "Latest result",
      sequence: 6,
      payload: {
        sourceSqlArtifactId: "artifact-sql-latest",
        queryFingerprint: "query-latest",
        columns: ["count"],
        rowCount: 1,
      },
    };
    artifacts.push(latestSql);

    const { rerender } = render(
      <ArtifactDock
        artifacts={artifacts}
        selectedArtifactId="artifact-sql-latest"
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Latest SQL SQL" }).getAttribute("aria-pressed"))
      .toBe("true");

    rerender(
      <ArtifactDock
        artifacts={[...artifacts, latestResult]}
        selectedArtifactId="artifact-result-latest"
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Latest result Result" }).getAttribute("aria-pressed"))
      .toBe("true");
    expect(agentApi.fetchArtifactPage).toHaveBeenCalledWith(
      "artifact-result-latest",
      expect.objectContaining({ page: 1 }),
      expect.any(AbortSignal),
    );
  });

  it("honors a selected artifact id from the conversation evidence chip", () => {
    const { container } = render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        selectedArtifactId="artifact-safety"
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Safety Safety" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("安全检查")).toBeTruthy();
    expect(screen.getByText("安全策略：已通过")).toBeTruthy();
    expect(screen.getByText("表结构提醒：0")).toBeTruthy();
    expect(container.querySelector(".conv-dock-safety-card .sql-code-block")).toBeTruthy();
    expect(container.querySelector(".conv-dock-safety-card .sql-token-keyword")?.textContent).toBe("SELECT");
  });

  it("renders dock content without owning split pane resize state", () => {
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        onOpenSqlConsole={vi.fn()}
        onOpenResultTab={vi.fn()}
      />,
    );

    const dock = screen.getByRole("complementary", { name: "Artifact dock" });

    expect(dock.getAttribute("style")).toBeNull();
    expect(screen.queryByRole("separator", { name: "调整工件区宽度" })).toBeNull();
  });
});
