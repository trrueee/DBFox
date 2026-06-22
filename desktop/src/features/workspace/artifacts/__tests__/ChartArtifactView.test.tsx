import type { CSSProperties } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChartArtifact } from "../../../../types/agentArtifact";
import { ChartArtifactView } from "../ChartArtifactView";

const echartsMock = vi.hoisted(() => ({
  options: [] as unknown[],
}));

vi.mock("echarts-for-react", () => ({
  default: ({ option, style }: { option: unknown; style?: CSSProperties }) => {
    echartsMock.options.push(option);
    return <div data-testid="echarts-mock" style={style} />;
  },
}));

describe("ChartArtifactView", () => {
  beforeEach(() => {
    cleanup();
    echartsMock.options = [];
  });

  it("renders chart source field formulas", () => {
    const artifact: ChartArtifact = {
      id: "chart-1",
      type: "chart",
      title: "GMV 趋势图",
      chartType: "bar",
      series: [{ label: "2026-06-01", value: 120 }],
      sourceRefs: [
        { label: "GMV", formula: "SUM(orders.amount)", field: "orders.amount" },
        { label: "日期", formula: "DATE(orders.created_at)", field: "orders.created_at" },
      ],
    };

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    expect(screen.getByText("GMV")).toBeTruthy();
    expect(screen.getByText("SUM(orders.amount)")).toBeTruthy();
    expect(screen.getByText("orders.amount")).toBeTruthy();
    expect(screen.getByText("日期")).toBeTruthy();
    expect(screen.getByText("DATE(orders.created_at)")).toBeTruthy();
  });

  it("passes pie chart data to ECharts without downgrading to bar", () => {
    const artifact: ChartArtifact = {
      id: "chart-pie",
      type: "chart",
      title: "GMV 构成",
      chartType: "pie",
      series: [
        { label: "personal", value: 120 },
        { label: "enterprise", value: 80 },
      ],
    };

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    const option = echartsMock.options[0] as { series: Array<{ type: string; data: unknown[] }> };
    expect(option.series[0].type).toBe("pie");
    expect(option.series[0].data).toEqual([
      { name: "personal", value: 120 },
      { name: "enterprise", value: 80 },
    ]);
    expect(screen.queryByText("折线")).toBeNull();
    expect(screen.queryByText("柱状")).toBeNull();
  });

  it("passes scatter chart pairs to ECharts", () => {
    const artifact: ChartArtifact = {
      id: "chart-scatter",
      type: "chart",
      title: "订单数与 GMV",
      chartType: "scatter",
      series: [
        { label: "10", value: 120 },
        { label: "20", value: 260 },
      ],
    };

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    const option = echartsMock.options[0] as {
      xAxis: { type: string };
      series: Array<{ type: string; data: unknown[] }>;
    };
    expect(option.xAxis.type).toBe("value");
    expect(option.series[0].type).toBe("scatter");
    expect(option.series[0].data).toEqual([[10, 120], [20, 260]]);
  });
});
