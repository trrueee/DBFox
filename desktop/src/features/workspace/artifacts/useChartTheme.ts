export interface ChartTheme {
  textColor: string;
  textMuted: string;
  textSecondary: string;
  borderColor: string;
  gridColor: string;
  panelBg: string;
  tooltipShadow: string;
  areaStart: string;
  areaEnd: string;
  tooltipFontSize: number;
  axisFontSize: number;
  chartColors: string[];
}

const CHART_COLOR_TOKENS = [
  "--agent-chart-1",
  "--agent-chart-2",
  "--agent-chart-3",
  "--agent-chart-4",
  "--agent-chart-5",
  "--agent-chart-6",
] as const;

function readToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function readFontSize(name: string, fallback: number): number {
  const parsed = Number.parseFloat(readToken(name, `${fallback}px`));
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function useChartTheme(): ChartTheme {
  return {
    textColor: readToken("--color-text-primary", "currentColor"),
    textMuted: readToken("--color-text-muted", "currentColor"),
    textSecondary: readToken("--color-text-secondary", "currentColor"),
    borderColor: readToken("--color-border", "currentColor"),
    gridColor: readToken("--agent-chart-grid", "currentColor"),
    panelBg: readToken("--color-panel", "transparent"),
    tooltipShadow: readToken("--agent-chart-tooltip-shadow", "none"),
    areaStart: readToken("--agent-chart-area-start", "transparent"),
    areaEnd: readToken("--agent-chart-area-end", "transparent"),
    tooltipFontSize: readFontSize("--ui-font-control", 12),
    axisFontSize: readFontSize("--ui-font-caption", 10),
    chartColors: CHART_COLOR_TOKENS.map((token) => readToken(token, "currentColor")),
  };
}
