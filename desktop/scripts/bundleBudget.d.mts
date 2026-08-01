export interface BundleMetric {
  file: string;
  rawBytes: number;
  gzipBytes: number;
}

export interface BundleReport {
  entry: BundleMetric;
  chart: BundleMetric;
}

export const ENTRY_BUDGET: Readonly<{ maxRawBytes: number; maxGzipBytes: number }>;
export const CHART_BUDGET: Readonly<{ maxRawBytes: number; maxGzipBytes: number }>;
export function inspectBundle(distDir: string): Readonly<BundleReport>;
export function formatBundleReport(report: BundleReport): string;
