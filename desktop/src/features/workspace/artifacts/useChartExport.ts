import { useCallback } from "react";
import type { RefObject } from "react";
import type ReactECharts from "echarts-for-react";

export function useChartExport(
  chartRef: RefObject<ReactECharts | null>,
  artifactId: string,
  chartType: string,
  backgroundColor: string,
  onToast: (message: string) => void,
) {
  return useCallback(() => {
    const chart = chartRef.current?.getEchartsInstance();
    if (!chart) {
      onToast("图表导出失败");
      return;
    }

    const url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor });
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${artifactId}-${chartType}.png`;
    anchor.click();
    onToast("已下载图表 PNG");
  }, [artifactId, backgroundColor, chartRef, chartType, onToast]);
}
