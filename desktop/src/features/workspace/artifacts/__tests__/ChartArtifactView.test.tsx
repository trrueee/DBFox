import type { CSSProperties } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChartArtifact } from "../../../../types/agentArtifact";
import { ChartArtifactView } from "../ChartArtifactView";

const echartsMock = vi.hoisted(() => ({
  options: [] as unknown[],
  resize: vi.fn(),
  getDataURL: vi.fn(() => "data:image/png;base64,test"),
}));

const chartDataMock = vi.hoisted(() => ({ fetch: vi.fn() }));

const liveChartMetadata = {
  consistency: "live_reexecution" as const,
  originalExecutedAt: "2026-07-20T00:00:00Z",
  viewExecutedAt: "2026-07-20T00:00:01Z",
  viewExecutionId: "view-chart",
  datasourceGeneration: 1,
  queryFingerprint: "query-chart",
};

vi.mock("../../../../lib/api/agent", () => ({
  agentApi: { fetchArtifactChartData: chartDataMock.fetch },
}));

vi.mock("echarts-for-react/lib/core", async () => {
  const React = await import("react");

  return {
    default: React.forwardRef(
      ({ option, style }: { option: unknown; style?: CSSProperties }, ref) => {
        echartsMock.options.push(option);
        React.useImperativeHandle(ref, () => ({
          getEchartsInstance: () => ({
            resize: echartsMock.resize,
            getDataURL: echartsMock.getDataURL,
          }),
        }));

    return <div data-testid="echarts-mock" style={style} />;
      },
    ),
  };
});

function makeChartArtifact(chartType: ChartArtifact["chartType"]): ChartArtifact {
  return {
    id: `chart-${chartType}`,
    type: "chart",
    title: "GMV 趋势",
    chartType,
    sourceResultArtifactId: "result-1",
    x: "day",
    y: ["gmv"],
    aggregation: "sum",
  };
}

describe("ChartArtifactView", () => {
  beforeEach(() => {
    cleanup();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    echartsMock.options = [];
    echartsMock.resize.mockClear();
    echartsMock.getDataURL.mockClear();
    chartDataMock.fetch.mockReset();
    chartDataMock.fetch.mockResolvedValue({
      series: [
        { label: "2026-06-01", value: 120 },
        { label: "2026-06-02", value: 260 },
      ],
      sampleSize: 2,
      truncated: false,
      ...liveChartMetadata,
    });
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

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("passes pie chart data to ECharts without downgrading to bar", async () => {
    const artifact: ChartArtifact = {
      id: "chart-pie",
      type: "chart",
      title: "GMV 构成",
      chartType: "pie",
      sourceResultArtifactId: "result-pie",
      x: "user_type",
      y: ["gmv"],
      aggregation: "sum",
    };

    chartDataMock.fetch.mockResolvedValueOnce({
      series: [{ label: "personal", value: 120 }, { label: "enterprise", value: 80 }],
      sampleSize: 2,
      truncated: false,
      ...liveChartMetadata,
    });

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    await waitFor(() => expect(echartsMock.options.length).toBeGreaterThan(1));
    const option = echartsMock.options.at(-1) as { series: Array<{ type: string; data: unknown[] }> };
    expect(option.series[0].type).toBe("pie");
    expect(option.series[0].data).toEqual([
      { name: "personal", value: 120 },
      { name: "enterprise", value: 80 },
    ]);
    expect(screen.queryByText("折线")).toBeNull();
    expect(screen.queryByText("柱状")).toBeNull();
  });

  it("passes scatter chart pairs to ECharts", async () => {
    const artifact: ChartArtifact = {
      id: "chart-scatter",
      type: "chart",
      title: "订单数与 GMV",
      chartType: "scatter",
      sourceResultArtifactId: "result-scatter",
      x: "order_count",
      y: ["gmv"],
      aggregation: "none",
    };

    chartDataMock.fetch.mockResolvedValueOnce({
      series: [{ label: "10", value: 120 }, { label: "20", value: 260 }],
      sampleSize: 2,
      truncated: false,
      ...liveChartMetadata,
    });

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    await waitFor(() => expect(echartsMock.options.length).toBeGreaterThan(1));
    const option = echartsMock.options.at(-1) as {
      xAxis: { type: string };
      series: Array<{ type: string; data: unknown[] }>;
    };
    expect(option.xAxis.type).toBe("value");
    expect(option.series[0].type).toBe("scatter");
    expect(option.series[0].data).toEqual([[10, 120], [20, 260]]);
  });

  it("uses agent chart tokens for palette, area styling, and chart text", async () => {
    const artifact: ChartArtifact = {
      id: "chart-area",
      type: "chart",
      title: "GMV 趋势",
      chartType: "area",
      sourceResultArtifactId: "result-area",
      x: "day",
      y: ["gmv"],
      aggregation: "sum",
    };

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    await waitFor(() => expect(echartsMock.options.length).toBeGreaterThan(1));
    const option = echartsMock.options.at(-1) as {
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

  it("derives axis names and labels from the reference-only chart definition", async () => {
    const artifact: ChartArtifact = {
      id: "chart-enriched",
      type: "chart",
      title: "GMV 趋势",
      chartType: "bar",
      sourceResultArtifactId: "result-enriched",
      x: "日期",
      y: ["GMV"],
      aggregation: "sum",
    };

    render(<ChartArtifactView artifact={artifact} onToast={vi.fn()} />);

    await waitFor(() => expect(echartsMock.options.length).toBeGreaterThan(1));
    const option = echartsMock.options.at(-1) as {
      xAxis: { name: string };
      yAxis: { name: string };
      series: Array<{ name: string; label: { show: boolean; position: string } }>;
    };
    expect(option.xAxis.name).toBe("日期");
    expect(option.yAxis.name).toBe("GMV");
    expect(option.series[0].name).toBe("GMV");
    expect(option.series[0].label).toEqual(expect.objectContaining({ show: true, position: "top" }));
  });

  it("can expand chart analysis height", () => {
    render(<ChartArtifactView artifact={makeChartArtifact("area")} onToast={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "展开分析" }));

    expect(screen.getByTestId("echarts-mock").parentElement?.className).toContain("is-expanded");
    expect(echartsMock.resize).toHaveBeenCalled();
  });

  it("exports chart png from the ECharts ref", () => {
    const onToast = vi.fn();
    render(<ChartArtifactView artifact={makeChartArtifact("bar")} onToast={onToast} />);

    fireEvent.click(screen.getByRole("button", { name: "PNG" }));

    expect(echartsMock.getDataURL).toHaveBeenCalledWith({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "rgb(255, 255, 255)",
    });
    expect(onToast).toHaveBeenCalledWith("已下载图表 PNG");
  });
});
