import { useEffect, useMemo, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import { AreaChart, BarChart3, Download, LineChart, PieChart, ScatterChart } from "lucide-react";
import type { ChartArtifact } from "../../../types/agentArtifact";

type PlotlyChartType = ChartArtifact["chartType"];

interface ChartArtifactViewProps {
  artifact: ChartArtifact;
  onToast: (message: string) => void;
}

const PLOTLY_CONFIG = {
  responsive: true,
  displaylogo: false,
  scrollZoom: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
};

const CHART_TYPE_META: Array<{ type: PlotlyChartType; label: string; icon: typeof LineChart }> = [
  { type: "line", label: "折线", icon: LineChart },
  { type: "bar", label: "柱状", icon: BarChart3 },
  { type: "area", label: "面积", icon: AreaChart },
  { type: "scatter", label: "散点", icon: ScatterChart },
  { type: "pie", label: "占比", icon: PieChart },
];

export function ChartArtifactView({ artifact, onToast }: ChartArtifactViewProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [chartType, setChartType] = useState<PlotlyChartType>(artifact.chartType);

  const labels = useMemo(() => artifact.series.map((p) => p.label), [artifact.series]);
  const values = useMemo(() => artifact.series.map((p) => p.value), [artifact.series]);

  const plotData = useMemo(() => {
    if (chartType === "pie") {
      return [
        {
          type: "pie",
          labels,
          values,
          hole: 0.42,
          textinfo: "label+percent",
          hovertemplate: "%{label}<br>%{value}<extra></extra>",
        },
      ];
    }

    const baseTrace = {
      x: labels,
      y: values,
      name: artifact.title,
      hovertemplate: `%{x}<br>%{y}${artifact.unit ? ` ${artifact.unit}` : ""}<extra></extra>`,
    };

    if (chartType === "bar") {
      return [
        {
          ...baseTrace,
          type: "bar",
          marker: { color: "#4F46E5", opacity: 0.86, line: { color: "#4338CA", width: 1 } },
        },
      ];
    }

    if (chartType === "scatter") {
      return [
        {
          ...baseTrace,
          type: "scatter",
          mode: "markers",
          marker: { color: "#4F46E5", size: 9, opacity: 0.82, line: { color: "#FFFFFF", width: 1.5 } },
        },
      ];
    }

    return [
      {
        ...baseTrace,
        type: "scatter",
        mode: "lines+markers",
        line: { color: "#4F46E5", width: 2.5, shape: "spline" },
        marker: { color: "#FFFFFF", size: 7, line: { color: "#4F46E5", width: 2 } },
        fill: chartType === "area" ? "tozeroy" : "none",
        fillcolor: "rgba(79, 70, 229, 0.12)",
      },
    ];
  }, [artifact.title, artifact.unit, chartType, labels, values]);

  const plotLayout = useMemo(() => ({
    autosize: true,
    height: 292,
    margin: { l: 48, r: 20, t: 12, b: 46 },
    paper_bgcolor: "rgba(255,255,255,0)",
    plot_bgcolor: "rgba(255,255,255,0)",
    font: { family: "Inter, ui-sans-serif, system-ui", size: 11, color: "#475569" },
    hoverlabel: { bgcolor: "#FFFFFF", bordercolor: "#E2E8F0", font: { color: "#334155" } },
    showlegend: chartType === "pie",
    xaxis: chartType === "pie" ? undefined : {
      automargin: true,
      tickangle: labels.length > 8 ? -28 : 0,
      tickfont: { size: 10, color: "#64748B" },
      gridcolor: "#F8FAFC",
      linecolor: "#E2E8F0",
      zerolinecolor: "#E2E8F0",
    },
    yaxis: chartType === "pie" ? undefined : {
      automargin: true,
      title: artifact.unit ? { text: artifact.unit, font: { size: 10, color: "#94A3B8" } } : undefined,
      tickfont: { size: 10, color: "#64748B" },
      gridcolor: "#EEF2F7",
      linecolor: "#E2E8F0",
      zerolinecolor: "#E2E8F0",
    },
  }), [artifact.unit, chartType, labels.length]);

  useEffect(() => {
    const root = chartRef.current;
    if (!root) return;
    let disposed = false;

    void Plotly.react(root, plotData, plotLayout, PLOTLY_CONFIG).catch(() => {
      if (!disposed) onToast("Plotly 图表渲染失败");
    });

    return () => {
      disposed = true;
      Plotly.purge(root);
    };
  }, [onToast, plotData, plotLayout]);

  const handleExportPng = async () => {
    const root = chartRef.current;
    if (!root) {
      onToast("图表导出失败");
      return;
    }
    try {
      await Plotly.downloadImage(root, {
        format: "png",
        filename: `${artifact.id}-${chartType}`,
        width: 1000,
        height: 560,
        scale: 2,
      });
      onToast("已下载 Plotly 图表 PNG");
    } catch {
      onToast("图表导出失败");
    }
  };

  return (
    <div className="hifi-ai-card hifi-chart-card mt-2">
      <div className="hifi-ai-card-header flex justify-between items-center">
        <span>{artifact.title}</span>
        <div className="flex items-center gap-1.5">
          {CHART_TYPE_META.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.type}
                className={`hifi-chart-type-btn ${chartType === item.type ? "active" : ""}`}
                onClick={() => setChartType(item.type)}
              >
                <Icon size={12} />
                <span>{item.label}</span>
              </button>
            );
          })}
          <button className="hifi-guide-btn-secondary flex items-center gap-1" style={{ height: "22px", fontSize: "9px" }} onClick={handleExportPng}>
            <Download size={9} /> PNG
          </button>
        </div>
      </div>
      {artifact.description && (
        <p className="text-[10px] text-slate-500 px-3 pt-1">{artifact.description}</p>
      )}
      <div className="hifi-chart-body">
        <div ref={chartRef} style={{ height: "292px", width: "100%" }} />
      </div>
    </div>
  );
}
