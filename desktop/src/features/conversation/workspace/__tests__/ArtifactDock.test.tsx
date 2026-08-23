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

vi.mock("echarts-for-react/esm/core", () => ({
  default: ({ option, style }: { option: unknown; style?: CSSProperties }) => {
    echartsMock.options.push(option);
    return <div data-testid="echarts-mock" style={style} />;
  },
}));

function trustedQueryArtifacts(): ConversationArtifact[] {
  return [
    {
      id: "artifact-sql",
      semantic_key: "sql_candidate",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "sql",
      visibility: "supporting",
      title: "SQL",
      status: "completed",
      payload: {
        sql: "SELECT id, amount FROM orders",
        safeSql: "SELECT id, amount FROM orders",
        dialect: "sqlite",
        queryFingerprint: "sql-orders",
      },
      provenance: {},
      relations: [],
    },
    {
      id: "artifact-safety",
      semantic_key: "safety_report",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "safety",
      visibility: "internal",
      title: "Safety",
      status: "completed",
      payload: {
        passed: true,
        canExecute: true,
        requiresApproval: false,
        guardrailResult: "passed",
        schemaWarningsCount: 0,
        safeSql: "SELECT id, amount FROM orders WHERE amount > 10",
      },
      provenance: {},
      relations: [{ relation: "validated_by", artifact_id: "artifact-sql" }],
    },
    {
      id: "artifact-result",
      semantic_key: "result_view_1",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "result_view",
      visibility: "primary",
      title: "Order result",
      status: "completed",
      payload: {
        sourceSqlArtifactId: "artifact-sql",
        queryFingerprint: "query-1",
        columns: ["id", "amount"],
        rowCount: 1,
      },
      provenance: {},
      relations: [{ relation: "executed_as", artifact_id: "artifact-sql" }],
    },
    {
      id: "artifact-chart",
      semantic_key: "chart_1",
      session_id: "conv",
      run_id: "run",
      version: 1,
      type: "chart",
      visibility: "primary",
      title: "Amount chart",
      status: "completed",
      payload: { chartType: "bar", sourceResultArtifactId: "artifact-result", x: "id", y: "amount", aggregation: "none" },
      provenance: {},
      relations: [{ relation: "visualized_as", artifact_id: "artifact-result" }],
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
      latencyMs: 1, consistency: "durable_snapshot",
      originalExecutedAt: "2026-07-20T00:00:00Z", viewExecutedAt: "2026-07-20T00:00:01Z",
      viewExecutionId: "view-dock", resourceVersion: 1, sourceFingerprint: "query-dock",
    });
    vi.mocked(agentApi.fetchArtifactChartData).mockResolvedValue({
      series: [{ label: "1", value: 20 }], sampleSize: 1, truncated: false,
      consistency: "durable_snapshot", originalExecutedAt: "2026-07-20T00:00:00Z",
      viewExecutedAt: "2026-07-20T00:00:01Z", viewExecutionId: "view-chart-dock",
      resourceVersion: 1, sourceFingerprint: "query-chart-dock",
    });
  });

  it("renders only core user-facing artifacts and keeps audit artifacts hidden", async () => {
    const onSelectArtifact = vi.fn();
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        selectedArtifactId="artifact-result"
        onOpenResultTab={vi.fn()}
        onSelectArtifact={onSelectArtifact}
      />,
    );

    expect(screen.getByRole("complementary", { name: "Artifact dock" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "SQL SQL" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Safety Safety" })).toBeNull();
    expect(screen.getByRole("button", { name: "Order result Result" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Amount chart Chart" })).toBeTruthy();
    expect(await screen.findByText("本页 1 / 共 1 行")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Amount chart Chart" }));

    expect(onSelectArtifact).toHaveBeenCalledWith("artifact-chart");
  });

  it("resolves a result SQL view only through its recorded source artifact id", async () => {
    const artifacts = trustedQueryArtifacts();
    artifacts.push({
      ...artifacts[0],
      id: "artifact-sql-unrelated",
      semantic_key: "sql_candidate_unrelated",
      payload: {
        sql: "SELECT secret FROM unrelated",
        safeSql: "SELECT secret FROM unrelated",
        dialect: "sqlite",
        queryFingerprint: "sql-unrelated",
      },
    });
    const onOpenSqlConsole = vi.fn();
    render(
      <ArtifactDock
        artifacts={artifacts}
        selectedArtifactId="artifact-result"
        onOpenResultTab={vi.fn()}
        onOpenSqlConsole={onOpenSqlConsole}
      />,
    );

    await screen.findByText("本页 1 / 共 1 行");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "SQL" }), { button: 0, ctrlKey: false });

    const sql = screen.getByLabelText("Order result 来源 SQL");
    expect(sql.textContent?.replace(/\s+/g, " ").trim()).toBe(
      "SELECT id, amount FROM orders",
    );
    expect(sql.textContent).not.toContain("unrelated");
    fireEvent.click(screen.getByRole("button", { name: "在 SQL 控制台打开" }));
    expect(onOpenSqlConsole).toHaveBeenCalledWith("SELECT id, amount FROM orders");
  });

  it("falls back to the latest primary artifact when selection points to supporting material", () => {
    const artifacts = trustedQueryArtifacts();
    const latestSql: ConversationArtifact = {
      ...artifacts[0],
      id: "artifact-sql-latest",
      semantic_key: "sql_candidate_latest",
      run_id: "run-latest",
      title: "Latest SQL",
      version: 2,
      payload: {
        sql: "SELECT COUNT(*) AS count FROM orders",
        safeSql: "SELECT COUNT(*) AS count FROM orders",
        dialect: "sqlite",
        queryFingerprint: "sql-orders-count",
      },
    };
    const latestResult: ConversationArtifact = {
      ...artifacts[2],
      id: "artifact-result-latest",
      semantic_key: "result_view_latest",
      run_id: "run-latest",
      title: "Latest result",
      version: 2,
      payload: {
        sourceSqlArtifactId: "artifact-sql-latest",
        queryFingerprint: "query-latest",
        columns: ["count"],
        rowCount: 1,
      },
    };
    artifacts.push(latestSql, latestResult);

    render(
      <ArtifactDock
        artifacts={artifacts}
        selectedArtifactId="artifact-sql-latest"
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Latest SQL SQL" })).toBeNull();
    expect(screen.getByRole("button", { name: "Latest result Result" }).getAttribute("aria-pressed"))
      .toBe("true");
    expect(agentApi.fetchArtifactPage).toHaveBeenCalledWith(
      "artifact-result-latest",
      expect.objectContaining({ page: 1 }),
      expect.any(AbortSignal),
    );
  });

  it("never promotes an internal safety record into the artifact dock", () => {
    render(
      <ArtifactDock
        artifacts={trustedQueryArtifacts()}
        selectedArtifactId="artifact-safety"
        onOpenResultTab={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Safety Safety" })).toBeNull();
    expect(screen.getByRole("button", { name: "Order result Result" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("renders dock content without owning split pane resize state", () => {
    render(
        <ArtifactDock
          artifacts={trustedQueryArtifacts()}
          onOpenResultTab={vi.fn()}
      />,
    );

    const dock = screen.getByRole("complementary", { name: "Artifact dock" });

    expect(dock.getAttribute("style")).toBeNull();
    expect(screen.queryByRole("separator", { name: "调整工件区宽度" })).toBeNull();
  });
});
