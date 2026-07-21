import { useEffect, useMemo, useRef, useState } from "react";
import ReactEChartsCore from "echarts-for-react/lib/core";
import { BarChart3, Download, LineChart, Maximize2, Minimize2 } from "lucide-react";
import { Button } from "../../../components/ui";
import { agentApi } from "../../../lib/api/agent";
import type { ChartArtifact, ChartArtifactType, ChartPoint } from "../../../types/agentArtifact";
import { ArtifactCard } from "./ArtifactCard";
import { useChartExport } from "./useChartExport";
import { useChartOption } from "./useChartOption";
import { echarts } from "./echartsCore";
import "./ArtifactViews.css";

interface ChartArtifactViewProps {
  artifact: ChartArtifact;
  onToast: (message: string) => void;
  compact?: boolean;
}

export function ChartArtifactView({ artifact, onToast, compact = false }: ChartArtifactViewProps) {
  const [chartType, setChartType] = useState<ChartArtifactType>(artifact.chartType);
  const [expanded, setExpanded] = useState(false);
  const [loaded, setLoaded] = useState<{
    artifactId: string;
    series: ChartPoint[];
    error: string | null;
    viewExecutedAt?: string;
  } | null>(null);
  const series = useMemo(
    () => loaded?.artifactId === artifact.id ? loaded.series : [],
    [artifact.id, loaded],
  );
  const loadError = loaded?.artifactId === artifact.id ? loaded.error : null;
  const chartRef = useRef<ReactEChartsCore | null>(null);

  const switchable = !compact && (artifact.chartType === "line" || artifact.chartType === "bar");
  const renderedArtifact = useMemo(() => ({ ...artifact, series }), [artifact, series]);
  const { option, theme } = useChartOption(renderedArtifact, chartType, compact);
  const handleExportPng = useChartExport(chartRef, artifact.id, chartType, theme.panelBg, onToast);

  useEffect(() => {
    chartRef.current?.getEchartsInstance()?.resize();
  }, [expanded, compact]);

  useEffect(() => {
    let active = true;
    void agentApi.fetchArtifactChartData(artifact.id).then((data) => {
      if (!active) return;
      setLoaded({
        artifactId: artifact.id,
        series: data.series,
        error: null,
        viewExecutedAt: data.viewExecutedAt,
      });
    }).catch((error: unknown) => {
      if (active) setLoaded({
        artifactId: artifact.id,
        series: [],
        error: error instanceof Error ? error.message : String(error),
      });
    });
    return () => {
      active = false;
    };
  }, [artifact.id]);

  return (
    <ArtifactCard
      className="chart-artifact-card"
      title={artifact.title}
      badge="图表"
      tone="chart"
      description={artifact.description}
      meta={loaded?.viewExecutedAt ? (
        <span className="artifact-pill artifact-pill--live">
          实时重查 {formatExecutionTime(loaded.viewExecutedAt)}
        </span>
      ) : undefined}
      compact={compact}
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
      {loadError && <div className="chart-artifact__loading" role="alert">{loadError}</div>}
      {!loadError && series.length === 0 && (
        <div className="chart-artifact__loading" role="status">正在读取图表数据…</div>
      )}
      <div
        className={[
          "chart-artifact__body",
          expanded ? "is-expanded" : "",
          compact ? "is-compact" : "",
        ].filter(Boolean).join(" ")}
        data-chart-id={artifact.id}
      >
        <ReactEChartsCore ref={chartRef} echarts={echarts} option={option} className="chart-artifact__echarts" />
      </div>
    </ArtifactCard>
  );
}

function formatExecutionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}
