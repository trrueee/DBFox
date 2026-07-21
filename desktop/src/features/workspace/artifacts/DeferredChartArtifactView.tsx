import { lazy, Suspense } from "react";
import type { ChartArtifact } from "../../../types/agentArtifact";

const ChartArtifactView = lazy(async () => {
  const module = await import("./ChartArtifactView");
  return { default: module.ChartArtifactView };
});

interface DeferredChartArtifactViewProps {
  artifact: ChartArtifact;
  onToast: (message: string) => void;
  compact?: boolean;
}

/**
 * Charts are an optional artifact type. Keep ECharts outside the conversation
 * and workspace bootstrap bundles until a chart is actually rendered.
 */
export function DeferredChartArtifactView(props: DeferredChartArtifactViewProps) {
  return (
    <Suspense fallback={<div className="chart-artifact__loading" role="status">正在载入图表…</div>}>
      <ChartArtifactView {...props} />
    </Suspense>
  );
}
