import { useState } from "react";
import ReactECharts from "echarts-for-react";
import { BarChart3, LineChart, Download } from "lucide-react";
import type { ChartArtifact, ChartArtifactType } from "../../../types/agentArtifact";
import { useTheme } from "../../../hooks/useTheme";

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

function scatterXValue(point: ChartArtifact["series"][number], index: number): number {
  const raw = point.x ?? point.label;
  const value = typeof raw === "number" ? raw : Number(raw);
  return Number.isFinite(value) ? value : index + 1;
}

export function ChartArtifactView({ artifact, onToast, compact = false }: ChartArtifactViewProps) {
  const [chartType, setChartType] = useState<ChartArtifactType>(artifact.chartType);
  const { theme } = useTheme();

  const labels = artifact.series.map((p) => p.label);
  const values = artifact.series.map((p) => p.value);
  const switchable = !compact && (artifact.chartType === "line" || artifact.chartType === "bar");

  // Get computed theme values for ECharts style sync
  const getThemeColor = (varName: string, fallback: string) => {
    if (typeof window === "undefined") return fallback;
    const val = window.getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    return val || fallback;
  };

  const textColor = getThemeColor("--color-text-primary", "#334155");
  const textMuted = getThemeColor("--color-text-muted", "#94A3B8");
  const textSecondary = getThemeColor("--color-text-secondary", "#64748B");
  const borderColor = getThemeColor("--color-border", "#E2E8F0");
  const borderLight = getThemeColor("--color-border-light", "#F1F5F9");
  const panelBg = getThemeColor("--color-panel", "#ffffff");

  const chartColors = theme === "dark"
    ? ["#E08244", "#38BDF8", "#F59E0B", "#34D399", "#F472B6", "#A78BFA"]
    : ["#4F46E5", "#0D7377", "#B45309", "#2E7D32", "#DB2777", "#7C3AED"];

  const primaryRgb = theme === "dark" ? "224, 130, 68" : "79, 70, 229";

  const option = chartType === "pie"
    ? {
        tooltip: {
          trigger: "item" as const,
          backgroundColor: panelBg,
          borderColor,
          textStyle: { color: textColor, fontSize: 12 },
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
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
          textStyle: { color: textColor, fontSize: 12 },
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        },
        grid: compact ? { left: 36, right: 14, top: 16, bottom: 30 } : { left: 48, right: 24, top: 24, bottom: 40 },
        xAxis: {
          type: chartType === "scatter" ? "value" as const : "category" as const,
          data: chartType === "scatter" ? undefined : labels,
          axisLabel: { color: textSecondary, fontSize: 10, rotate: labels.length > 6 && !compact ? 30 : 0 },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: borderColor } },
        },
        yAxis: {
          type: "value" as const,
          axisLabel: { color: textSecondary, fontSize: 10 },
          splitLine: { lineStyle: { color: borderLight } },
          name: artifact.unit || "",
          nameTextStyle: { color: textMuted, fontSize: 10 },
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
                    ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `rgba(${primaryRgb}, 0.15)` }, { offset: 1, color: `rgba(${primaryRgb}, 0)` }] } }
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
    <div className={`hifi-ai-card hifi-chart-card mt-2 ${compact ? "is-compact" : ""}`}>
      <div className="hifi-ai-card-header flex justify-between items-center">
        <span>{artifact.title}</span>
        {!compact && (
          <div className="flex items-center gap-1.5">
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
          </div>
        )}
      </div>
      {artifact.description && (
        <p className="hifi-artifact-description px-3 pt-1">{artifact.description}</p>
      )}
      {artifact.sourceRefs && artifact.sourceRefs.length > 0 && (
        <div className="hifi-artifact-meta grid px-3 pt-2">
          {artifact.sourceRefs.map((sourceRef) => (
            <div key={`${sourceRef.label}-${sourceRef.field}`} className="flex flex-wrap items-center gap-1.5">
              <span className="hifi-artifact-pill">{sourceRef.label}</span>
              <span className="font-mono">{sourceRef.formula}</span>
              <span className="hifi-artifact-muted-text">-&gt;</span>
              <span className="font-mono">{sourceRef.field}</span>
            </div>
          ))}
        </div>
      )}
      <div className="hifi-chart-body" data-chart-id={artifact.id}>
        <ReactECharts option={option} style={chartStyle} />
      </div>
    </div>
  );
}
