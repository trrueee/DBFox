import { useMemo } from "react";
import type { ChartArtifactType, RenderedChartArtifact } from "../../../types/agentArtifact";
import { type ChartTheme, useChartTheme } from "./useChartTheme";

function scatterXValue(point: RenderedChartArtifact["series"][number], index: number): number {
  const raw = point.x ?? point.label;
  const value = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(value) ? value : index + 1;
}

function yAxisName(artifact: RenderedChartArtifact): string {
  return artifact.y[0] || "";
}

function shouldShowDataLabels(artifact: RenderedChartArtifact, chartType: ChartArtifactType, compact: boolean): boolean {
  if (compact || chartType === "scatter") return false;
  return artifact.series.length > 0 && artifact.series.length <= 8;
}

export function buildChartOption(
  artifact: RenderedChartArtifact,
  chartType: ChartArtifactType,
  compact: boolean,
  theme: ChartTheme,
) {
  const labels = artifact.series.map((point) => point.label);
  const values = artifact.series.map((point) => point.value);
  const showDataLabels = shouldShowDataLabels(artifact, chartType, compact);
  const seriesName = artifact.y[0] || artifact.title;

  if (chartType === "pie") {
    return {
      tooltip: {
        trigger: "item" as const,
        backgroundColor: theme.panelBg,
        borderColor: theme.borderColor,
        textStyle: { color: theme.textColor, fontSize: theme.tooltipFontSize },
        boxShadow: theme.tooltipShadow,
      },
      color: theme.chartColors,
      series: [
        {
          name: seriesName,
          type: "pie",
          radius: compact ? ["35%", "68%"] : ["32%", "70%"],
          center: ["50%", "50%"],
          label: {
            show: showDataLabels || !compact,
            color: theme.textSecondary,
            fontSize: theme.axisFontSize,
            formatter: "{b}\n{d}%",
          },
          labelLine: { show: showDataLabels || !compact, lineStyle: { color: theme.borderColor } },
          data: artifact.series.map((point) => ({ name: point.label, value: point.value })),
        },
      ],
    };
  }

  return {
    tooltip: {
      trigger: chartType === "scatter" ? "item" as const : "axis" as const,
      axisPointer: { type: chartType === "bar" ? "shadow" as const : "line" as const },
      backgroundColor: theme.panelBg,
      borderColor: theme.borderColor,
      textStyle: { color: theme.textColor, fontSize: theme.tooltipFontSize },
      boxShadow: theme.tooltipShadow,
    },
    color: theme.chartColors,
    grid: compact ? { left: 40, right: 16, top: 18, bottom: 34 } : { left: 56, right: 28, top: 28, bottom: 48 },
    xAxis: {
      type: chartType === "scatter" ? "value" as const : "category" as const,
      data: chartType === "scatter" ? undefined : labels,
      axisLabel: { color: theme.textSecondary, fontSize: theme.axisFontSize, rotate: labels.length > 6 && !compact ? 30 : 0 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: theme.borderColor } },
      name: artifact.x,
      nameGap: 24,
      nameTextStyle: { color: theme.textMuted, fontSize: theme.axisFontSize },
    },
    yAxis: {
      type: "value" as const,
      axisLabel: { color: theme.textSecondary, fontSize: theme.axisFontSize },
      splitLine: { lineStyle: { color: theme.gridColor } },
      name: yAxisName(artifact),
      nameTextStyle: { color: theme.textMuted, fontSize: theme.axisFontSize },
    },
    series: [
      {
        name: seriesName,
        type: chartType === "area" ? "line" : chartType,
        data: chartType === "scatter"
          ? artifact.series.map((point, index) => [scatterXValue(point, index), point.value])
          : values,
        itemStyle: { color: theme.chartColors[0] },
        label: {
          show: showDataLabels,
          position: "top",
          color: theme.textSecondary,
          fontSize: theme.axisFontSize,
        },
        ...(chartType === "line" || chartType === "area"
          ? {
              smooth: true,
              lineStyle: { width: 2.5 },
              areaStyle: chartType === "area"
                ? {
                    color: {
                      type: "linear",
                      x: 0,
                      y: 0,
                      x2: 0,
                      y2: 1,
                      colorStops: [
                        { offset: 0, color: theme.areaStart },
                        { offset: 1, color: theme.areaEnd },
                      ],
                    },
                  }
                : undefined,
              symbol: "circle",
              symbolSize: compact ? 4 : 6,
            }
          : chartType === "bar"
            ? {
                barWidth: Math.max(10, Math.min(32, 320 / Math.max(labels.length, 1))),
                borderRadius: [4, 4, 0, 0],
              }
            : {
                symbolSize: compact ? 8 : 11,
              }),
      },
    ],
  };
}

export function useChartOption(
  artifact: RenderedChartArtifact,
  chartType: ChartArtifactType,
  compact: boolean,
) {
  const theme = useChartTheme();
  const option = useMemo(
    () => buildChartOption(artifact, chartType, compact, theme),
    [artifact, chartType, compact, theme],
  );

  return { option, theme };
}
