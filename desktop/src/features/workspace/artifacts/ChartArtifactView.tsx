import { useState } from "react";
import ReactECharts from "echarts-for-react";
import { BarChart3, LineChart, Download } from "lucide-react";
import type { ChartArtifact, ChartArtifactType } from "../../../types/agentArtifact";
import { ArtifactCard } from "./ArtifactCard";

interface ChartArtifactViewProps {
  artifact: ChartArtifact;
  onToast: (message: string) => void;
  compact?: boolean;
}

type EChartsDomElement = HTMLElement & {
  _echarts_instance?: {
    getDataURL: (options: { type: "png"; pixelRatio: number; backgroundColor: string }) => string;
  };
};

const CHART_COLOR_TOKENS = [
  "--agent-chart-1",
  "--agent-chart-2",
  "--agent-chart-3",
  "--agent-chart-4",
  "--agent-chart-5",
  "--agent-chart-6",
] as const;

function scatterXValue(point: ChartArtifact["series"][number], index: number): number {
  const raw = point.x ?? point.label;
  const value = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(value) ? value : index + 1;
}

export function ChartArtifactView({ artifact, onToast, compact = false }: ChartArtifactViewProps) {
  const [chartType, setChartType] = useState<ChartArtifactType>(artifact.chartType);

  const labels = artifact.series.map((p) => p.label);
  const values = artifact.series.map((p) => p.value);
  const switchable = !compact && (artifact.chartType === "line" || artifact.chartType === "bar");

  // Get computed theme values for ECharts style sync
  const getThemeColor = (varName: string, fallback: string) => {
    if (typeof window === "undefined") return fallback;
    const val = window.getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    return val || fallback;
  };

  const getThemeFontSize = (varName: string, fallback: number) => {
    const value = getThemeColor(varName, `${fallback}px`);
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const textColor = getThemeColor("--color-text-primary", "currentColor");
  const textMuted = getThemeColor("--color-text-muted", "currentColor");
  const textSecondary = getThemeColor("--color-text-secondary", "currentColor");
  const borderColor = getThemeColor("--color-border", "currentColor");
  const borderLight = getThemeColor("--agent-chart-grid", "currentColor");
  const panelBg = getThemeColor("--color-panel", "transparent");
  const tooltipShadow = getThemeColor("--agent-chart-tooltip-shadow", "none");
  const areaStart = getThemeColor("--agent-chart-area-start", "transparent");
  const areaEnd = getThemeColor("--agent-chart-area-end", "transparent");
  const tooltipFontSize = getThemeFontSize("--ui-font-control", 12);
  const axisFontSize = getThemeFontSize("--ui-font-caption", 10);
  const chartColors = CHART_COLOR_TOKENS.map((token) => getThemeColor(token, "currentColor"));

  const option = chartType === "pie"
    ? {
        tooltip: {
          trigger: "item" as const,
          backgroundColor: panelBg,
          borderColor,
          textStyle: { color: textColor, fontSize: tooltipFontSize },
          boxShadow: tooltipShadow,
        },
        color: chartColors,
        series: [
          {
            name: artifact.title,
            type: "pie",
            radius: compact ? ["35%", "68%"] : ["32%", "70%"],
            data: artifact.series.map((point) => ({ name: point.label, value: point.value })),
          },
        ],
      }
    : {
        tooltip: {
          trigger: chartType === "scatter" ? "item" as const : "axis" as const,
          backgroundColor: panelBg,
          borderColor,
          textStyle: { color: textColor, fontSize: tooltipFontSize },
          boxShadow: tooltipShadow,
        },
        color: chartColors,
        grid: compact ? { left: 36, right: 14, top: 16, bottom: 30 } : { left: 48, right: 24, top: 24, bottom: 40 },
        xAxis: {
          type: chartType === "scatter" ? "value" as const : "category" as const,
          data: chartType === "scatter" ? undefined : labels,
          axisLabel: { color: textSecondary, fontSize: axisFontSize, rotate: labels.length > 6 && !compact ? 30 : 0 },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: borderColor } },
        },
        yAxis: {
          type: "value" as const,
          axisLabel: { color: textSecondary, fontSize: axisFontSize },
          splitLine: { lineStyle: { color: borderLight } },
          name: artifact.unit || "",
          nameTextStyle: { color: textMuted, fontSize: axisFontSize },
        },
        series: [
          {
            name: artifact.title,
            type: chartType === "area" ? "line" : chartType,
            data: chartType === "scatter"
              ? artifact.series.map((point, index) => [scatterXValue(point, index), point.value])
              : values,
            itemStyle: { color: chartColors[0] },
            ...(chartType === "line" || chartType === "area"
              ? {
                  smooth: true,
                  lineStyle: { width: 2.5 },
                  areaStyle: chartType === "area"
                    ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: areaStart }, { offset: 1, color: areaEnd }] } }
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

  const handleExportPng = () => {
    const chartElement = document.querySelector(`[data-chart-id="${artifact.id}"]`) as EChartsDomElement | null;
    const chartInstance = chartElement?._echarts_instance;
    if (chartInstance) {
      const url = chartInstance.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: panelBg });
      const a = document.createElement("a");
      a.href = url;
      a.download = `${artifact.id}-${chartType}.png`;
      a.click();
      onToast("已下载图表 PNG");
    } else {
      onToast("图表导出失败");
    }
  };

  const chartStyle = {
    height: compact ? "180px" : "280px",
    width: "100%",
  };

  return (
    <ArtifactCard
      title={artifact.title}
      badge="图表"
      tone="chart"
      description={artifact.description}
      compact={compact}
      meta={
        artifact.sourceRefs && artifact.sourceRefs.length > 0
          ? artifact.sourceRefs.map((sourceRef) => (
              <div key={`${sourceRef.label}-${sourceRef.field}`} className="flex flex-wrap items-center gap-1.5">
                <span className="hifi-artifact-pill">{sourceRef.label}</span>
                <span className="font-mono">{sourceRef.formula}</span>
                <span className="hifi-artifact-muted-text">-&gt;</span>
                <span className="font-mono">{sourceRef.field}</span>
              </div>
            ))
          : undefined
      }
      actions={
        !compact ? (
          <>
            {switchable && (
              <>
                <button
                  className={`hifi-chart-type-btn ${chartType === "line" ? "active" : ""}`}
                  onClick={() => setChartType("line")}
                >
                  <LineChart size={12} />
                  <span>折线</span>
                </button>
                <button
                  className={`hifi-chart-type-btn ${chartType === "bar" ? "active" : ""}`}
                  onClick={() => setChartType("bar")}
                >
                  <BarChart3 size={12} />
                  <span>柱状</span>
                </button>
              </>
            )}
            <button className="hifi-guide-btn-secondary hifi-artifact-action-btn-sm flex items-center gap-1" onClick={handleExportPng}>
              <Download size={9} /> PNG
            </button>
          </>
        ) : undefined
      }
    >
      <div className="hifi-chart-body" data-chart-id={artifact.id}>
        <ReactECharts option={option} style={chartStyle} />
      </div>
    </ArtifactCard>
  );
}
