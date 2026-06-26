import { useEffect, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { BarChart3, Download, LineChart, Maximize2, Minimize2 } from "lucide-react";
import { Button } from "../../../components/ui";
import type { ChartArtifact, ChartArtifactType } from "../../../types/agentArtifact";
import { ArtifactCard } from "./ArtifactCard";
import { useChartExport } from "./useChartExport";
import { useChartOption } from "./useChartOption";
import "./ArtifactViews.css";

interface ChartArtifactViewProps {
  artifact: ChartArtifact;
  onToast: (message: string) => void;
  compact?: boolean;
}

export function ChartArtifactView({ artifact, onToast, compact = false }: ChartArtifactViewProps) {
  const [chartType, setChartType] = useState<ChartArtifactType>(artifact.chartType);
  const [expanded, setExpanded] = useState(false);
  const chartRef = useRef<ReactECharts | null>(null);

  const switchable = !compact && (artifact.chartType === "line" || artifact.chartType === "bar");
  const { option, theme } = useChartOption(artifact, chartType, compact);
  const handleExportPng = useChartExport(chartRef, artifact.id, chartType, theme.panelBg, onToast);
  const metaItems = [
    ...(typeof artifact.sampleSize === "number"
      ? [
          <div key="sample-size" className="chart-artifact__meta-row">
            <span className="artifact-pill">样本 {artifact.sampleSize} 行</span>
          </div>,
        ]
      : []),
    ...((artifact.sourceRefs || []).map((sourceRef) => (
      <div key={`${sourceRef.label}-${sourceRef.field}`} className="chart-artifact__meta-row">
        <span className="artifact-pill">{sourceRef.label}</span>
        <span className="chart-artifact__formula">{sourceRef.formula}</span>
        <span className="chart-artifact__muted">-&gt;</span>
        <span className="chart-artifact__formula">{sourceRef.field}</span>
      </div>
    ))),
  ];

  useEffect(() => {
    chartRef.current?.getEchartsInstance()?.resize();
  }, [expanded, compact]);

  return (
    <ArtifactCard
      className="chart-artifact-card"
      title={artifact.title}
      badge="图表"
      tone="chart"
      description={artifact.description}
      compact={compact}
      meta={metaItems.length > 0 ? metaItems : undefined}
      actions={
        !compact ? (
          <>
            {switchable && (
              <>
                <Button
                  type="button"
                  variant={chartType === "line" ? "secondary" : "outline"}
                  size="sm"
                  className="artifact-action-button artifact-action-button--sm chart-artifact__type-button"
                  aria-pressed={chartType === "line"}
                  onClick={() => setChartType("line")}
                >
                  <LineChart size={12} />
                  <span>折线</span>
                </Button>
                <Button
                  type="button"
                  variant={chartType === "bar" ? "secondary" : "outline"}
                  size="sm"
                  className="artifact-action-button artifact-action-button--sm chart-artifact__type-button"
                  aria-pressed={chartType === "bar"}
                  onClick={() => setChartType("bar")}
                >
                  <BarChart3 size={12} />
                  <span>柱状</span>
                </Button>
              </>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="artifact-action-button artifact-action-button--sm"
              aria-pressed={expanded}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? <Minimize2 size={9} /> : <Maximize2 size={9} />}
              {expanded ? "收起分析" : "展开分析"}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="artifact-action-button artifact-action-button--sm"
              onClick={handleExportPng}
            >
              <Download size={9} /> PNG
            </Button>
          </>
        ) : undefined
      }
    >
      <div
        className={[
          "chart-artifact__body",
          expanded ? "is-expanded" : "",
          compact ? "is-compact" : "",
        ].filter(Boolean).join(" ")}
        data-chart-id={artifact.id}
      >
        <ReactECharts ref={chartRef} option={option} className="chart-artifact__echarts" />
      </div>
    </ArtifactCard>
  );
}
