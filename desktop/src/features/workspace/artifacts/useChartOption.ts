import { useMemo } from "react";
import type { ChartArtifact, ChartArtifactType } from "../../../types/agentArtifact";
import { type ChartTheme, useChartTheme } from "./useChartTheme";

function scatterXValue(point: ChartArtifact["series"][number], index: number): number {
  const raw = point.x ?? point.label;
  const value = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(value) ? value : index + 1;
}

export function buildChartOption(
  artifact: ChartArtifact,
  chartType: ChartArtifactType,
  compact: boolean,
  theme: ChartTheme,
) {
  const labels = artifact.series.map((point) => point.label);
  const values = artifact.series.map((point) => point.value);

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
          name: artifact.title,
          type: "pie",
          radius: compact ? ["35%", "68%"] : ["32%", "70%"],
          data: artifact.series.map((point) => ({ name: point.label, value: point.value })),
        },
      ],
    };
  }

  return {
    tooltip: {
      trigger: chartType === "scatter" ? "item" as const : "axis" as const,
      backgroundColor: theme.panelBg,
      borderColor: theme.borderColor,
      textStyle: { color: theme.textColor, fontSize: theme.tooltipFontSize },
      boxShadow: theme.tooltipShadow,
    },
    color: theme.chartColors,
    grid: compact ? { left: 36, right: 14, top: 16, bottom: 30 } : { left: 48, right: 24, top: 24, bottom: 40 },
    xAxis: {
      type: chartType === "scatter" ? "value" as const : "category" as const,
      data: chartType === "scatter" ? undefined : labels,
      axisLabel: { color: theme.textSecondary, fontSize: theme.axisFontSize, rotate: labels.length > 6 && !compact ? 30 : 0 },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: theme.borderColor } },
    },
    yAxis: {
      type: "value" as const,
      axisLabel: { color: theme.textSecondary, fontSize: theme.axisFontSize },
      splitLine: { lineStyle: { color: theme.gridColor } },
      name: artifact.unit || "",
      nameTextStyle: { color: theme.textMuted, fontSize: theme.axisFontSize },
    },
    series: [
      {
        name: artifact.title,
        type: chartType === "area" ? "line" : chartType,
        data: chartType === "scatter"
          ? artifact.series.map((point, index) => [scatterXValue(point, index), point.value])
          : values,
        itemStyle: { color: theme.chartColors[0] },
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
  artifact: ChartArtifact,
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
