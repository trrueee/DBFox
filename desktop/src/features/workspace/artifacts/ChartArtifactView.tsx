import { useEffect, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { BarChart3, Download, LineChart, Maximize2, Minimize2 } from "lucide-react";
import type { ChartArtifact, ChartArtifactType } from "../../../types/agentArtifact";
import { ArtifactCard } from "./ArtifactCard";
import { useChartExport } from "./useChartExport";
import { useChartOption } from "./useChartOption";

interface ChartArtifactViewProps {
  artifact: ChartArtifact;
  onToast: (message: string) => void;
  compact?: boolean;
}

const chartFillStyle = { height: "100%", width: "100%" };

export function ChartArtifactView({ artifact, onToast, compact = false }: ChartArtifactViewProps) {
  const [chartType, setChartType] = useState<ChartArtifactType>(artifact.chartType);
  const [expanded, setExpanded] = useState(false);
  const chartRef = useRef<ReactECharts | null>(null);

  const switchable = !compact && (artifact.chartType === "line" || artifact.chartType === "bar");
  const { option, theme } = useChartOption(artifact, chartType, compact);
  const handleExportPng = useChartExport(chartRef, artifact.id, chartType, theme.panelBg, onToast);

  useEffect(() => {
    chartRef.current?.getEchartsInstance()?.resize();
  }, [expanded, compact]);

  return (
    <ArtifactCard
      className="hifi-chart-card"
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
                  type="button"
                  className={`hifi-chart-type-btn ${chartType === "line" ? "active" : ""}`}
                  onClick={() => setChartType("line")}
                >
                  <LineChart size={12} />
                  <span>折线</span>
                </button>
                <button
                  type="button"
                  className={`hifi-chart-type-btn ${chartType === "bar" ? "active" : ""}`}
                  onClick={() => setChartType("bar")}
                >
                  <BarChart3 size={12} />
                  <span>柱状</span>
                </button>
              </>
            )}
            <button
              type="button"
              className="hifi-guide-btn-secondary hifi-artifact-action-btn-sm flex items-center gap-1"
              aria-pressed={expanded}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? <Minimize2 size={9} /> : <Maximize2 size={9} />}
              {expanded ? "收起分析" : "展开分析"}
            </button>
            <button type="button" className="hifi-guide-btn-secondary hifi-artifact-action-btn-sm flex items-center gap-1" onClick={handleExportPng}>
              <Download size={9} /> PNG
            </button>
          </>
        ) : undefined
      }
    >
      <div className={`hifi-chart-body ${expanded ? "is-expanded" : ""}`} data-chart-id={artifact.id}>
        <ReactECharts ref={chartRef} option={option} style={chartFillStyle} />
      </div>
    </ArtifactCard>
  );
}
