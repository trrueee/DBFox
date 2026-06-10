import { useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { BarChart3, LineChart, PieChart } from "lucide-react";
import { isNumericLike, toChartNumber } from "../lib/chart-utils";

type ChartType = "bar" | "line" | "pie";

interface ChartPanelProps {
  columns: string[];
  rows: Record<string, unknown>[];
  initialType?: string;
  initialX?: string;
  initialY?: string;
}

// Light lab palette for charts
const CHART_COLORS = ["#2D3B8C", "#0D7377", "#B45309", "#2E7D32", "#4A5BC0", "#14A3A8", "#D97706", "#5C5D60"];

function normalizeChartType(value?: string): ChartType {
  return value === "line" || value === "pie" || value === "bar" ? value : "bar";
}

export function ChartPanel({ columns, rows, initialType, initialX, initialY }: ChartPanelProps) {
  const [chartType, setChartType] = useState<ChartType>(normalizeChartType(initialType));
  const [labelCol, setLabelCol] = useState(initialX || "");
  const [valueCol, setValueCol] = useState(initialY || "");

  const numericCols = useMemo(
    () => columns.filter((c) => rows.some((r) => isNumericLike(r[c]))),
    [columns, rows],
  );

  const stringCols = useMemo(
    () => columns.filter((c) => !numericCols.includes(c)),
    [columns, numericCols],
  );

  const effectiveLabel = labelCol || stringCols[0] || columns[0] || "";
  const effectiveValue = valueCol || numericCols[0] || columns[1] || columns[0] || "";

  const option = useMemo(() => {
    if (rows.length === 0 || !effectiveLabel || !effectiveValue) return null;

    const labels = rows.map((r) => String(r[effectiveLabel] ?? ""));
    const values = rows.map((r) => toChartNumber(r[effectiveValue]));

    if (chartType === "pie") {
      return {
        color: CHART_COLORS,
        tooltip: { trigger: "item" as const },
        legend: {
          type: "scroll" as const,
          orient: "vertical" as const,
          right: 10,
          top: 20,
          bottom: 20,
          textStyle: { color: "#5C5D60", fontSize: 12, fontFamily: "Inter, sans-serif" },
        },
        series: [
          {
            type: "pie",
            radius: ["40%", "70%"],
            center: ["40%", "50%"],
            avoidLabelOverlap: false,
            itemStyle: {
              borderRadius: 4,
              borderColor: "#FFFFFF",
              borderWidth: 2,
            },
            label: { show: false },
            emphasis: { label: { show: true, fontWeight: "bold", color: "#1A1A1C" } },
            data: labels.map((name, i) => ({ name, value: values[i] })),
          },
        ],
      };
    }

    return {
      color: [CHART_COLORS[0], CHART_COLORS[1]],
      tooltip: { trigger: "axis" as const },
      legend: {
        show: true,
        textStyle: { color: "#5C5D60", fontSize: 12, fontFamily: "Inter, sans-serif" },
        top: 0,
      },
      grid: { left: "3%", right: "4%", bottom: "3%", top: 40, containLabel: true },
      xAxis: {
        type: "category" as const,
        data: labels,
        axisLabel: {
          color: "#5C5D60",
          rotate: labels.length > 8 ? 30 : 0,
          fontSize: 11,
          fontFamily: "Inter, sans-serif",
          interval: 0,
          overflow: "truncate",
          width: 100,
        },
        axisLine: { lineStyle: { color: "#D4D2CC" } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value" as const,
        axisLabel: { color: "#5C5D60", fontSize: 11, fontFamily: "Inter, sans-serif" },
        splitLine: { lineStyle: { color: "#E8E6E1" } },
      },
      series: [
        {
          name: effectiveValue,
          type: chartType,
          data: values,
          smooth: chartType === "line",
          itemStyle: {
            borderRadius: chartType === "bar" ? [6, 6, 0, 0] : undefined,
            color: CHART_COLORS[0],
          },
          lineStyle: chartType === "line" ? { color: CHART_COLORS[0], width: 2 } : undefined,
          areaStyle:
            chartType === "line"
              ? {
                  color: {
                    type: "linear",
                    x: 0, y: 0, x2: 0, y2: 1,
                    colorStops: [
                      { offset: 0, color: "rgba(45,59,140,0.15)" },
                      { offset: 1, color: "rgba(45,59,140,0.01)" },
                    ],
                  },
                }
              : undefined,
        },
      ],
    };
  }, [rows, chartType, effectiveLabel, effectiveValue]);

  if (rows.length === 0) {
    return (
      <div className="bg-card border border-border rounded-lg" style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
        没有可用于图表展示的数据
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Controls */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <div className="inline-flex bg-secondary rounded-sm p-0.5 gap-px">
          {([["bar", BarChart3], ["line", LineChart], ["pie", PieChart]] as const).map(([type, Icon]) => (
            <button
              key={type}
              className={`pill-tab ${chartType === type ? "active" : ""}`}
              onClick={() => setChartType(type)}
            >
              <Icon size={13} />
              {type === "bar" ? "柱状" : type === "line" ? "折线" : "饼图"}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <label style={{ color: "var(--text-secondary)", fontSize: "0.78rem" }}>标签:</label>
          <select
            className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            value={effectiveLabel}
            onChange={(e) => setLabelCol(e.target.value)}
            style={{ width: "auto" }}
          >
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <label style={{ color: "var(--text-secondary)", fontSize: "0.78rem" }}>数值:</label>
          <select
            className="h-7 rounded-sm border border-input bg-transparent px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            value={effectiveValue}
            onChange={(e) => setValueCol(e.target.value)}
            style={{ width: "auto" }}
          >
            {(numericCols.length > 0 ? numericCols : columns).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>

      {option && (
        <div className="bg-card border border-border rounded-lg" style={{ padding: 8, background: "var(--bg-surface)" }}>
          <ReactECharts
            option={option}
            style={{ height: 300, width: "100%" }}
            opts={{ renderer: "svg" }}
          />
        </div>
      )}
    </div>
  );
}
