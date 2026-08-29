const DLC_ID = "dbfox.visualization";
const ARTIFACT_TYPE = "dbfox.visualization.document";
const AUTHORED_DATASET_TYPE = "dbfox.visualization.authored_dataset";
const LEGACY_DATA_CHART_TYPE = "dbfox.data.chart";
const DATAFRAME_TYPE = "dbfox.dataframe.v1";
const DATASET_NAME = "dbfox_source";

let React;

function ensureStylesheet() {
  if (typeof document === "undefined") return;
  if (document.querySelector(`link[data-dbfox-dlc="${DLC_ID}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = new URL("./index.css", import.meta.url).href;
  link.dataset.dbfoxDlc = DLC_ID;
  document.head.append(link);
}

function parsePayload(value) {
  if (!isRecord(value) || value.specVersion !== "1.0") {
    throw new Error("Invalid Visualization Artifact payload");
  }
  if (typeof value.title !== "string" || typeof value.insight !== "string") {
    throw new Error("Visualization title and insight are required");
  }
  if (!isRecord(value.source) || !["artifact", "inline"].includes(value.source.kind)) {
    throw new Error("Visualization source is invalid");
  }
  if (!Array.isArray(value.blocks)
      || !value.blocks.some((block) => ["chart", "metric"].includes(block?.kind))) {
    throw new Error("Visualization requires at least one chart or metric block");
  }
  return value;
}

function parseAuthoredDataset(value) {
  if (!isRecord(value)
      || !["model_knowledge", "user_provided"].includes(value.provenance)
      || !Array.isArray(value.records)
      || value.records.length === 0) {
    throw new Error("Invalid authored Visualization dataset payload");
  }
  return value;
}

function parseLegacyDataChart(value) {
  if (!isRecord(value)) throw new Error("Invalid historical Data chart payload");
  const chartType = String(value.chartType || "");
  if (!["line", "bar", "pie", "scatter", "area"].includes(chartType)) {
    throw new Error("Historical Data chart type is invalid");
  }
  const sourceResultArtifactId = String(value.sourceResultArtifactId || "").trim();
  const x = String(value.x || "").trim();
  const y = Array.isArray(value.y) ? String(value.y[0] || "").trim() : "";
  if (!sourceResultArtifactId || !x || !y) {
    throw new Error("Historical Data chart field mapping is incomplete");
  }
  return {
    chartType,
    sourceResultArtifactId,
    x,
    y,
    aggregation: value.aggregation === "sum" ? "sum" : null,
    title: typeof value.title === "string" ? value.title : null,
  };
}

function legacyDocument(artifact, payload) {
  const aggregate = payload.aggregation || undefined;
  const common = {
    data: { name: DATASET_NAME },
    encoding: {
      tooltip: [
        { field: payload.x, type: "nominal" },
        { field: payload.y, type: "quantitative", aggregate },
      ],
    },
  };
  if (payload.chartType === "pie") {
    common.mark = { type: "arc", innerRadius: 36 };
    common.encoding.theta = { field: payload.y, type: "quantitative", aggregate };
    common.encoding.color = { field: payload.x, type: "nominal" };
  } else {
    common.mark = payload.chartType === "scatter"
      ? { type: "point", filled: true, size: 72 }
      : { type: payload.chartType, point: payload.chartType === "line" };
    common.encoding.x = {
      field: payload.x,
      type: payload.chartType === "scatter" ? "quantitative" : "nominal",
    };
    common.encoding.y = { field: payload.y, type: "quantitative", aggregate };
  }
  return {
    specVersion: "1.0",
    title: payload.title || artifact.title,
    description: "由旧版 Data 图表迁移的只读可视化。",
    insight: artifact.summary || "该图表保留其原始 Result 工件作为数据来源。",
    source: {
      kind: "artifact",
      artifactId: payload.sourceResultArtifactId,
      representationType: DATAFRAME_TYPE,
      pageSize: 500,
    },
    layout: { columns: 1, density: "comfortable" },
    blocks: [{
      id: "legacy_chart",
      kind: "chart",
      span: 1,
      grammar: "vega-lite",
      minHeight: 280,
      spec: common,
    }],
  };
}

function VisualizationArtifactView({ artifact, payload, context }) {
  const [reload, setReload] = React.useState(0);
  const [state, setState] = React.useState(() => (
    payload.source.kind === "inline"
      ? { status: "ready", rows: payload.source.records, read: null, error: null }
      : { status: "loading", rows: [], read: null, error: null }
  ));

  React.useEffect(() => {
    if (payload.source.kind !== "artifact") {
      setState({ status: "ready", rows: payload.source.records, read: null, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setState({ status: "loading", rows: [], read: null, error: null });
    context.representations.read(
      payload.source.artifactId,
      payload.source.representationType,
      {
        operation: "page",
        parameters: {
          page: 1,
          page_size: payload.source.pageSize,
          count_mode: "none",
        },
      },
      controller.signal,
    ).then((result) => {
      if (controller.signal.aborted) return;
      try {
        setState({ status: "ready", rows: rowsFromDataFrame(result), read: result, error: null });
      } catch (error) {
        setState({ status: "error", rows: [], read: null, error });
      }
    }, (error) => {
      if (!controller.signal.aborted) setState({ status: "error", rows: [], read: null, error });
    });
    return () => controller.abort();
  }, [artifact.id, artifact.version, context.representations, payload.source, reload]);

  const sourceArtifact = payload.source.kind === "artifact"
    ? context.resolveArtifact?.(payload.source.artifactId)
    : null;
  const authoredProvenance = sourceArtifact?.type === AUTHORED_DATASET_TYPE
    ? sourceArtifact.payload?.provenance
    : null;
  const sourceLabel = authoredProvenance === "user_provided"
    ? "用户提供"
    : authoredProvenance === "model_knowledge"
      ? "模型知识"
      : payload.source.kind === "artifact"
        ? (state.read?.consistency === "live_reexecution"
            ? "实时重查"
            : state.read?.consistency === "durable_snapshot"
              ? "耐久快照"
              : "来源工件")
    : payload.source.provenance === "user_provided" ? "用户提供" : "模型知识";
  const openSource = sourceArtifact && context.openArtifact
    ? () => context.openArtifact(sourceArtifact)
    : null;
  const visibleBlocks = state.rows.length > 0
    ? payload.blocks
    : payload.blocks.filter((block) => (
        block.kind === "text"
        || (block.kind === "metric" && block.field == null)
      ));

  return React.createElement(
    "article",
    {
      className: `dbfox-visualization dbfox-visualization--${context.surface}`,
      "aria-label": payload.title,
    },
    React.createElement(
      "header",
      { className: "dbfox-visualization__header" },
      React.createElement(
        "div",
        { className: "dbfox-visualization__heading" },
        React.createElement("span", { className: "dbfox-visualization__eyebrow" }, "Visual analysis"),
        React.createElement("h3", null, payload.title),
        payload.description ? React.createElement("p", null, payload.description) : null,
      ),
      React.createElement(
        "div",
        { className: "dbfox-visualization__source" },
        React.createElement("span", { className: "dbfox-visualization__source-badge" }, sourceLabel),
        openSource ? React.createElement(
          "button",
          { type: "button", className: "dbfox-visualization__source-action", onClick: openSource },
          React.createElement(SourceIcon),
          "查看源工件",
        ) : null,
      ),
    ),
    React.createElement(
      "p",
      { className: "dbfox-visualization__insight" },
      React.createElement(InsightIcon),
      React.createElement("span", null, payload.insight),
    ),
    state.status === "loading" ? React.createElement(VisualizationLoading) : null,
    state.status === "error" ? React.createElement(VisualizationError, {
      onRetry: payload.source.kind === "artifact"
        ? () => setReload((value) => value + 1)
        : null,
    }) : null,
    state.status === "ready" && state.rows.length === 0
      ? React.createElement(VisualizationEmpty)
      : null,
    state.status === "ready" && visibleBlocks.length > 0 ? React.createElement(
      "div",
      {
        className: `dbfox-visualization__grid dbfox-visualization__grid--${payload.layout?.density || "comfortable"} dbfox-visualization__grid--columns-${payload.layout?.columns || 2}`,
      },
      visibleBlocks.map((block) => React.createElement(VisualizationBlock, {
        key: block.id,
        block,
        rows: state.rows,
        insight: payload.insight,
        surface: context.surface,
        onToast: context.onToast,
      })),
    ) : null,
    state.status === "ready" && state.rows.length > 0
      ? React.createElement(DataTableFallback, {
          rows: state.rows,
          fields: dataFrameFieldNames(state.read),
        })
      : null,
    state.status === "ready" && state.read?.payload?.has_next_page
      ? React.createElement(
        "p",
        { className: "dbfox-visualization__notice" },
        `图形使用前 ${state.rows.length.toLocaleString()} 行；完整数据请在源工件的表格视图中查看。`,
      )
      : null,
  );
}

function VisualizationBlock({ block, rows, insight, surface, onToast }) {
  const spanClass = `dbfox-visualization__span-${block.span || 1}`;
  if (block.kind === "metric") {
    const value = metricValue(block, rows);
    return React.createElement(
      "section",
      { className: `dbfox-visualization__metric dbfox-visualization__metric--${block.emphasis} ${spanClass}` },
      React.createElement("span", null, block.label),
      React.createElement("strong", null, formatMetric(value, block)),
      block.unit ? React.createElement("small", null, block.unit) : null,
    );
  }
  if (block.kind === "text") {
    return React.createElement(
      "section",
      { className: `dbfox-visualization__text dbfox-visualization__text--${block.tone} ${spanClass}` },
      block.title ? React.createElement("h4", null, block.title) : null,
      React.createElement("p", null, block.text),
    );
  }
  if (block.kind === "table") {
    const fields = Array.isArray(block.fields) && block.fields.length
      ? block.fields
      : Object.keys(rows[0] || {}).slice(0, 12);
    return React.createElement(
      "section",
      { className: `dbfox-visualization__table-block ${spanClass}` },
      block.title ? React.createElement("h4", null, block.title) : null,
      block.description ? React.createElement("p", null, block.description) : null,
      React.createElement(DataTable, {
        rows: rows.slice(0, Number(block.limit) || 10),
        fields,
        emptyLabel: "当前来源没有数据行",
      }),
    );
  }
  return React.createElement(
    "section",
    { className: `dbfox-visualization__chart-block ${spanClass}` },
    block.title ? React.createElement("h4", null, block.title) : null,
    block.description ? React.createElement("p", null, block.description) : null,
    React.createElement(VegaChart, { block, rows, insight, surface, onToast }),
  );
}

function VegaChart({ block, rows, insight, surface, onToast }) {
  const containerRef = React.useRef(null);
  const viewRef = React.useRef(null);
  const [status, setStatus] = React.useState("loading");
  const [error, setError] = React.useState(null);
  const [interaction, setInteraction] = React.useState(null);

  React.useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    let disposed = false;
    let resizeObserver;
    setStatus("loading");
    setError(null);
    import("./vendor/vega-runtime.js").then(async ({
      View,
      Warn,
      compile,
      expressionInterpreter,
      parse,
    }) => {
      if (disposed) return;
      const themed = themedSpec(block.spec, block.grammar, block.minHeight, element);
      const runtimeSpec = block.grammar === "vega-lite"
        ? compile(themed, { config: vegaConfig(element) }).spec
        : themed;
      const runtime = parse(runtimeSpec, null, { ast: true });
      const view = new View(runtime, {
        container: element,
        renderer: surface === "inline" ? "svg" : "canvas",
        hover: true,
        expr: expressionInterpreter,
        loader: deniedLoader(),
        logLevel: Warn,
      });
      view.tooltip((_handler, _event, _item, value) => {
        if (!disposed) {
          setInteraction(value == null || value === ""
            ? null
            : { blockId: block.id, value });
        }
      }).description(block.description || block.title || insight);
      view.data(DATASET_NAME, rows);
      viewRef.current = view;
      await view.runAsync();
      if (disposed) {
        view.finalize();
        return;
      }
      setStatus("ready");
      resizeObserver = new ResizeObserver(() => {
        void view.resize().runAsync();
      });
      resizeObserver.observe(element);
    }).catch((caught) => {
      if (!disposed) {
        setStatus("error");
        setError(caught);
      }
    });
    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      viewRef.current?.finalize();
      viewRef.current = null;
    };
  }, [block, insight, rows, surface]);

  const exportChart = async (type) => {
    const view = viewRef.current;
    if (!view) return;
    try {
      const url = type === "svg"
        ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(await view.toSVG())}`
        : await view.toImageURL("png", 2);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${safeFileName(block.title || block.id)}.${type}`;
      anchor.click();
      onToast(`已导出 ${type.toUpperCase()} 图形`);
    } catch {
      onToast("图形导出失败");
    }
  };

  return React.createElement(
    "figure",
    { className: "dbfox-visualization__figure", "aria-label": block.description || block.title || insight },
    surface === "workspace" ? React.createElement(
      "div",
      { className: "dbfox-visualization__chart-actions", "aria-label": "图形操作" },
      React.createElement("button", { type: "button", disabled: status !== "ready", onClick: () => exportChart("png") }, "PNG"),
      React.createElement("button", { type: "button", disabled: status !== "ready", onClick: () => exportChart("svg") }, "SVG"),
    ) : null,
    status === "loading" ? React.createElement("div", { className: "dbfox-visualization__chart-loading", role: "status" }, "正在绘制图形…") : null,
    status === "error" ? React.createElement(
      "div",
      { className: "dbfox-visualization__chart-error", role: "alert" },
      React.createElement("strong", null, "图形暂时无法呈现"),
      React.createElement("span", null, userError(error)),
    ) : null,
    React.createElement("div", {
      ref: containerRef,
      className: `dbfox-visualization__vega ${visualizationHeightClass(block.minHeight)}`,
      tabIndex: 0,
    }),
    interaction?.blockId === block.id
      ? React.createElement(ChartInteractionDetails, { value: interaction.value })
      : null,
    React.createElement("figcaption", { className: "dbfox-visualization__sr-only" }, block.description || insight),
  );
}

function ChartInteractionDetails({ value }) {
  const entries = tooltipEntries(value);
  return React.createElement(
    "section",
    { className: "dbfox-visualization__tooltip", "aria-label": "当前数据点" },
    React.createElement("strong", null, "当前数据点"),
    React.createElement(
      "dl",
      null,
      entries.map(([key, item]) => React.createElement(
        "div",
        { key },
        React.createElement("dt", null, key),
        React.createElement("dd", null, formatTooltipValue(item)),
      )),
    ),
  );
}

function tooltipEntries(value) {
  if (isRecord(value)) return Object.entries(value).slice(0, 12);
  return [["值", value]];
}

function formatTooltipValue(value) {
  if (value == null) return "—";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return text.length > 160 ? `${text.slice(0, 157)}…` : text;
}

function DataTableFallback({ rows, fields: declaredFields, defaultOpen = false }) {
  const fields = declaredFields.length ? declaredFields : Object.keys(rows[0] || {});
  return React.createElement(
    "details",
    { className: "dbfox-visualization__data-fallback", open: defaultOpen || undefined },
    React.createElement("summary", null, "查看无障碍数据表"),
    React.createElement(DataTable, { rows, fields, emptyLabel: "当前来源没有数据行" }),
  );
}

function DataTable({ rows, fields, emptyLabel }) {
  return React.createElement(
    "div",
    { className: "dbfox-visualization__table-scroll" },
    React.createElement(
      "table",
      null,
      React.createElement(
        "thead",
        null,
        React.createElement(
          "tr",
          null,
          fields.map((field) => React.createElement(
            "th",
            { key: field, scope: "col" },
            field,
          )),
        ),
      ),
      React.createElement(
        "tbody",
        null,
        rows.length
          ? rows.map((row, index) => React.createElement(
            "tr",
            { key: index },
            fields.map((field) => React.createElement(
              "td",
              { key: field },
              displayValue(row[field]),
            )),
          ))
          : React.createElement(
            "tr",
            null,
            React.createElement("td", { colSpan: Math.max(fields.length, 1) }, emptyLabel),
          ),
      ),
    ),
  );
}

function AuthoredDatasetView({ artifact, payload, context }) {
  const sourceLabel = payload.provenance === "user_provided" ? "用户提供" : "模型知识";
  const fields = Object.keys(payload.records[0] || {});
  return React.createElement(
    "article",
    {
      className: `dbfox-visualization dbfox-visualization--dataset dbfox-visualization--${context.surface}`,
      "aria-label": artifact.title,
    },
    React.createElement(
      "header",
      { className: "dbfox-visualization__header" },
      React.createElement(
        "div",
        { className: "dbfox-visualization__heading" },
        React.createElement("span", { className: "dbfox-visualization__eyebrow" }, "Authored dataset"),
        React.createElement("h3", null, artifact.title),
        React.createElement(
          "p",
          null,
          "这是可视化使用的独立耐久事实集，可单独检查并追溯其声明来源。",
        ),
      ),
      React.createElement(
        "div",
        { className: "dbfox-visualization__source" },
        React.createElement("span", { className: "dbfox-visualization__source-badge" }, sourceLabel),
        React.createElement(
          "span",
          { className: "dbfox-visualization__dataset-count" },
          `${payload.records.length.toLocaleString()} 行`,
        ),
      ),
    ),
    React.createElement(DataTableFallback, {
      rows: payload.records,
      fields,
      defaultOpen: true,
    }),
  );
}

function VisualizationLoading() {
  return React.createElement(
    "div",
    { className: "dbfox-visualization__loading", role: "status" },
    React.createElement("span", { className: "dbfox-visualization__spinner", "aria-hidden": true }),
    React.createElement("span", null, "正在读取可视化数据…"),
  );
}

function VisualizationEmpty() {
  return React.createElement(
    "div",
    { className: "dbfox-visualization__empty", role: "status" },
    React.createElement("strong", null, "来源暂时没有数据行"),
    React.createElement("span", null, "指标会保留显式值；依赖行数据的图形将在来源产生记录后显示。"),
  );
}

function VisualizationError({ onRetry }) {
  return React.createElement(
    "div",
    { className: "dbfox-visualization__error", role: "alert" },
    React.createElement("strong", null, "无法读取可视化数据"),
    React.createElement("span", null, "源工件可能已变化、不可用或不再提供所需 Representation。"),
    onRetry ? React.createElement("button", { type: "button", onClick: onRetry }, "重试") : null,
  );
}

function rowsFromDataFrame(result) {
  if (result?.representation_type !== DATAFRAME_TYPE || result.operation !== "page") {
    throw new Error("Source did not return a DataFrame page");
  }
  const page = result.payload;
  if (!isRecord(page) || !Array.isArray(page.fields)) throw new Error("Invalid DataFrame page");
  const fields = page.fields.map((field) => {
    if (!isRecord(field) || typeof field.name !== "string" || !Array.isArray(field.values)) {
      throw new Error("Invalid DataFrame field");
    }
    return field;
  });
  const rowCount = fields[0]?.values.length || 0;
  if (fields.some((field) => field.values.length !== rowCount)) throw new Error("Inconsistent DataFrame vectors");
  return Array.from({ length: rowCount }, (_, index) => Object.fromEntries(
    fields.map((field) => [field.name, field.values[index] ?? null]),
  ));
}

function dataFrameFieldNames(result) {
  const fields = result?.payload?.fields;
  return Array.isArray(fields)
    ? fields.flatMap((field) => typeof field?.name === "string" ? [field.name] : [])
    : [];
}

function visualizationHeightClass(value) {
  const height = Number(value) || 280;
  if (height <= 220) return "dbfox-visualization__vega--sm";
  if (height <= 340) return "dbfox-visualization__vega--md";
  if (height <= 500) return "dbfox-visualization__vega--lg";
  return "dbfox-visualization__vega--xl";
}

function metricValue(block, rows) {
  if (block.field == null) return block.value;
  const values = rows.map((row) => row[block.field]).filter((value) => value != null);
  if (block.aggregation === "count") return values.length;
  if (block.aggregation === "distinct") return new Set(values.map((value) => JSON.stringify(value))).size;
  const numbers = values.map(Number).filter(Number.isFinite);
  if (!numbers.length) return null;
  if (block.aggregation === "sum") return numbers.reduce((sum, value) => sum + value, 0);
  if (block.aggregation === "mean") return numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
  if (block.aggregation === "median") {
    const ordered = [...numbers].sort((left, right) => left - right);
    const middle = Math.floor(ordered.length / 2);
    return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
  }
  if (block.aggregation === "min") return Math.min(...numbers);
  if (block.aggregation === "max") return Math.max(...numbers);
  return values[0] ?? null;
}

function formatMetric(value, block) {
  if (value == null) return "—";
  if (block.format === "text") return String(value);
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (block.format === "percent") return new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 }).format(number);
  if (block.format === "currency") return new Intl.NumberFormat(undefined, { style: "currency", currency: block.unit || "CNY", maximumFractionDigits: 2 }).format(number);
  if (block.format === "compact") return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(number);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: block.format === "integer" ? 0 : 2 }).format(number);
}

function themedSpec(input, grammar, minHeight, element) {
  const spec = structuredClone(input);
  delete spec.$schema;
  delete spec.config;
  delete spec.background;
  if (grammar === "vega-lite") {
    spec.data = { name: DATASET_NAME };
    spec.autosize = { type: "fit", contains: "padding", resize: true };
    spec.width = "container";
    if (spec.height == null) spec.height = Math.max(160, minHeight - 32);
  } else {
    spec.background = "transparent";
    if (spec.width == null) spec.width = Math.max(240, element.clientWidth || 640);
    if (spec.height == null) spec.height = Math.max(160, minHeight - 32);
  }
  return spec;
}

function vegaConfig(element) {
  const style = getComputedStyle(element);
  const font = style.fontFamily || "sans-serif";
  const text = css(style, "--color-text-primary");
  const muted = css(style, "--color-text-secondary");
  const border = css(style, "--color-border");
  const primary = css(style, "--color-primary");
  const palette = [
    primary,
    css(style, "--color-info"),
    css(style, "--color-success"),
    css(style, "--color-warning"),
    css(style, "--color-danger"),
    css(style, "--color-accent"),
  ].filter(Boolean);
  return {
    background: "transparent",
    font,
    view: { stroke: null },
    axis: {
      domainColor: border,
      gridColor: border,
      gridOpacity: 0.55,
      labelColor: muted,
      labelFont: font,
      labelFontSize: 11,
      labelLimit: 120,
      tickColor: border,
      titleColor: text,
      titleFont: font,
      titleFontSize: 12,
      titleFontWeight: 500,
    },
    legend: {
      labelColor: muted,
      labelFont: font,
      titleColor: text,
      titleFont: font,
      symbolStrokeWidth: 2,
    },
    range: palette.length ? { category: palette, ordinal: palette } : undefined,
    mark: { color: primary },
    line: { strokeWidth: 2.25, point: true },
    area: { opacity: 0.2 },
    bar: { cornerRadiusTopLeft: 3, cornerRadiusTopRight: 3 },
  };
}

function deniedLoader() {
  const reject = async () => { throw new Error("External visualization assets are disabled"); };
  return { load: reject, sanitize: reject };
}

function SourceIcon() {
  return React.createElement(
    "svg",
    { viewBox: "0 0 16 16", width: 14, height: 14, "aria-hidden": true },
    React.createElement("path", { d: "M2.5 3.5h11v9h-11zM2.5 6.5h11M6 6.5v6", fill: "none", stroke: "currentColor", strokeWidth: "1.25" }),
  );
}

function InsightIcon() {
  return React.createElement(
    "svg",
    { viewBox: "0 0 16 16", width: 16, height: 16, "aria-hidden": true },
    React.createElement("path", { d: "M8 1.75a4.75 4.75 0 0 0-2.84 8.56c.45.34.71.85.71 1.39h4.26c0-.54.26-1.05.71-1.39A4.75 4.75 0 0 0 8 1.75ZM6 14h4", fill: "none", stroke: "currentColor", strokeWidth: "1.25", strokeLinecap: "round" }),
  );
}

function css(style, name) {
  return style.getPropertyValue(name).trim();
}

function displayValue(value) {
  if (value == null) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function safeFileName(value) {
  return String(value || "visualization").replace(/[^\p{L}\p{N}._-]+/gu, "-").slice(0, 80) || "visualization";
}

function userError(error) {
  return error instanceof Error && error.message ? error.message : "请检查可视化规格和源数据。";
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function register(host) {
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("DBFox React host is unavailable");
  ensureStylesheet();
  host.artifactViews.register({
    id: "dbfox.visualization.document",
    title: "可视化",
    priority: 100,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: ARTIFACT_TYPE, schemaVersions: [1, 2] }],
    parsePayload,
    render: (artifact, payload, context) => React.createElement(
      VisualizationArtifactView,
      { artifact, payload, context },
    ),
  });
  host.artifactViews.register({
    id: "dbfox.visualization.authored-dataset",
    title: "来源数据",
    priority: 90,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: AUTHORED_DATASET_TYPE, schemaVersions: [1] }],
    parsePayload: parseAuthoredDataset,
    render: (artifact, payload, context) => React.createElement(
      AuthoredDatasetView,
      { artifact, payload, context },
    ),
  });
  host.artifactViews.register({
    id: "dbfox.visualization.legacy-data-chart",
    title: "历史图表",
    priority: 20,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: LEGACY_DATA_CHART_TYPE, schemaVersions: [1] }],
    parsePayload: parseLegacyDataChart,
    render: (artifact, payload, context) => React.createElement(
      VisualizationArtifactView,
      { artifact, payload: legacyDocument(artifact, payload), context },
    ),
  });
}

export function deactivate() {
  if (typeof document !== "undefined") document.querySelectorAll(`link[data-dbfox-dlc="${DLC_ID}"]`).forEach((link) => link.remove());
  React = undefined;
}
