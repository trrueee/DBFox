declare module "plotly.js-dist-min" {
  type PlotlyTrace = Record<string, unknown>;
  type PlotlyLayout = Record<string, unknown>;
  type PlotlyConfig = Record<string, unknown>;

  const Plotly: {
    newPlot: (
      root: HTMLElement,
      data: PlotlyTrace[],
      layout?: PlotlyLayout,
      config?: PlotlyConfig,
    ) => Promise<HTMLElement>;
    react: (
      root: HTMLElement,
      data: PlotlyTrace[],
      layout?: PlotlyLayout,
      config?: PlotlyConfig,
    ) => Promise<HTMLElement>;
    purge: (root: HTMLElement) => void;
    downloadImage: (
      root: HTMLElement,
      options: { format?: "png" | "svg" | "jpeg" | "webp"; filename?: string; width?: number; height?: number; scale?: number },
    ) => Promise<string>;
  };

  export default Plotly;
}
