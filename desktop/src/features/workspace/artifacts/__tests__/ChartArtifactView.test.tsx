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
    const style = document.documentElement.style;
    style.setProperty("--color-text-primary", "rgb(15, 23, 42)");
    style.setProperty("--color-text-muted", "rgb(100, 116, 139)");
    style.setProperty("--color-text-secondary", "rgb(71, 85, 105)");
    style.setProperty("--color-border", "rgb(226, 232, 240)");
    style.setProperty("--color-panel", "rgb(255, 255, 255)");
    style.setProperty("--ui-font-control", "12px");
    style.setProperty("--ui-font-caption", "10px");
    style.setProperty("--agent-chart-1", "rgb(79, 70, 229)");
    style.setProperty("--agent-chart-2", "rgb(13, 115, 119)");
    style.setProperty("--agent-chart-3", "rgb(180, 83, 9)");
    style.setProperty("--agent-chart-4", "rgb(46, 125, 50)");
    style.setProperty("--agent-chart-5", "rgb(219, 39, 119)");
    style.setProperty("--agent-chart-6", "rgb(124, 58, 237)");
    style.setProperty("--agent-chart-grid", "rgb(241, 245, 249)");
    style.setProperty("--agent-chart-area-start", "rgba(79, 70, 229, 0.15)");
    style.setProperty("--agent-chart-area-end", "rgba(79, 70, 229, 0)");
    style.setProperty("--agent-chart-tooltip-shadow", "0 4px 12px rgba(15, 23, 42, 0.14)");
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

  it("uses agent chart tokens for palette, area styling, and chart text", () => {
    const artifact: ChartArtifact = {
      id: "chart-area",
      type: "chart",
      title: "GMV 趋势",
      chartType: "area",
      series: [
        { label: "2026-06-01", value: 120 },
        { label: "2026-06-02", value: 260 },
      ],
    };

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    const option = echartsMock.options[0] as {
      color: string[];
      tooltip: { boxShadow: string; textStyle: { fontSize: number } };
      xAxis: { axisLabel: { fontSize: number } };
      yAxis: {
        axisLabel: { fontSize: number };
        nameTextStyle: { fontSize: number };
        splitLine: { lineStyle: { color: string } };
      };
      series: Array<{
        itemStyle: { color: string };
        areaStyle: { color: { colorStops: Array<{ offset: number; color: string }> } };
      }>;
    };

    expect(option.color).toEqual([
      "rgb(79, 70, 229)",
      "rgb(13, 115, 119)",
      "rgb(180, 83, 9)",
      "rgb(46, 125, 50)",
      "rgb(219, 39, 119)",
      "rgb(124, 58, 237)",
    ]);
    expect(option.series[0].itemStyle.color).toBe("rgb(79, 70, 229)");
    expect(option.series[0].areaStyle.color.colorStops).toEqual([
      { offset: 0, color: "rgba(79, 70, 229, 0.15)" },
      { offset: 1, color: "rgba(79, 70, 229, 0)" },
    ]);
    expect(option.tooltip.boxShadow).toBe("0 4px 12px rgba(15, 23, 42, 0.14)");
    expect(option.tooltip.textStyle.fontSize).toBe(12);
    expect(option.xAxis.axisLabel.fontSize).toBe(10);
    expect(option.yAxis.axisLabel.fontSize).toBe(10);
    expect(option.yAxis.nameTextStyle.fontSize).toBe(10);
    expect(option.yAxis.splitLine.lineStyle.color).toBe("rgb(241, 245, 249)");
  });
});
