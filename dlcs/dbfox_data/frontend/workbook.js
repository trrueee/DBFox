const KIND = "dbfox.core.attachment";
export const WORKBOOK_VIEW_TYPE = "dbfox.data.workbook";

// One conversion at the third-party view boundary. Query data never comes back
// from this model, and the native renderer is only ever mounted in read-only mode.
export function fortuneSheets(projection, formatValue) {
  return projection.sheets.map((sheet, index) => {
    const cells = sheet.cells.map(cell => {
      const style = projection.styles[cell.style], font = style.font;
      return { r: cell.r, c: cell.c, v: { v: cell.v,
        m: cell.v == null ? "" : cell.type === "text" ? String(cell.v) : formatValue(style.format, cell.v),
        ct: cell.type === "text" && String(cell.v).includes("\n")
          ? { fa: "@", t: "inlineStr", s: [{ v: cell.v, ff: font.name, fs: font.size, fc: font.color || "#23364B" }] }
          : { fa: style.format, t: cell.type === "date" ? "d" : cell.type === "text" ? "s" : "n" },
        ...(cell.formula ? { f: cell.formula } : {}), ff: font.name || "Microsoft YaHei", fs: font.size || 11,
        bl: font.bold ? 1 : 0, it: font.italic ? 1 : 0, fc: font.color || "#23364B", ...(style.fill ? { bg: style.fill } : {}),
        ht: ({ center: 0, left: 1, right: 2 })[style.align.horizontal] ?? (cell.type === "text" ? 1 : 2),
        vt: ({ center: 0, top: 1, bottom: 2 })[style.align.vertical] ?? 0, tb: style.align.wrap ? "2" : "0",
      } };
    });
    const merge = {}, positions = new Map(cells.map(cell => [`${cell.r}_${cell.c}`, cell]));
    for (const area of sheet.merges) {
      merge[`${area.r}_${area.c}`] = area;
      for (let r = area.r; r < area.r + area.rs; r++) for (let c = area.c; c < area.c + area.cs; c++) {
        const key = `${r}_${c}`;
        let entry = positions.get(key);
        if (!entry) { entry = { r, c, v: {} }; cells.push(entry); positions.set(key, entry); }
        entry.v.mc = r === area.r && c === area.c ? area : { r: area.r, c: area.c };
      }
    }
    const borderInfo = sheet.cells.filter(cell => Object.keys(projection.styles[cell.style].borders).length).map(cell => {
      const value = { row_index: cell.r, col_index: cell.c };
      for (const [side, border] of Object.entries(projection.styles[cell.style].borders)) value[({ top: "t", right: "r", bottom: "b", left: "l" })[side]] = { style: 1, color: border.color || "#D5DFE9" };
      return { rangeType: "cell", value };
    });
    return { id: `sheet-${index}`, name: sheet.name, status: 1, order: index,
      luckysheet_select_save: [{ row: [0, 0], column: [0, 0], row_focus: 0, column_focus: 0 }],
      row: Math.max(sheet.rows + 10, 80), column: Math.max(sheet.columns, 12), celldata: cells,
      config: { merge, rowlen: sheet.rowHeights, columnlen: sheet.columnWidths, borderInfo,
        rowhidden: Object.fromEntries((sheet.hiddenRows ?? []).map(row => [row, 0])) },
      frozen: sheet.freeze.rows || sheet.freeze.columns ? {
        type: sheet.freeze.rows && sheet.freeze.columns ? "rangeBoth" : sheet.freeze.rows ? "rangeRow" : "rangeColumn",
        range: { row_focus: Math.max(sheet.freeze.rows - 1, 0), column_focus: Math.max(sheet.freeze.columns - 1, 0) },
      } : undefined };
  });
}

function locator(value) {
  if (!value) return null;
  const location = JSON.parse(value);
  if (!location || typeof location.sheet !== "string" || !Number.isInteger(location.row) || !Number.isInteger(location.column)
    || location.row < 0 || location.column < 0 || location.row > 10000 || location.column > 127) throw new Error("来源单元格定位无效或超出预览范围。");
  return location;
}

export function registerWorkbookPreview(host, React) {
  const h = React.createElement;
  function WorkbookDock({ view }) {
    const object = view.target?.type === "object" ? view.target.object : null;
    const key = `${view.sessionId}:${object?.id}:${object?.version}`;
    const [state, setState] = React.useState({ key: "" });
    const [loaded, setLoaded] = React.useState({ key: "" });
    const [runtime, setRuntime] = React.useState(null);
    const api = React.useRef(null);
    const grid = React.useRef(null);
    React.useEffect(() => {
      const controller = new AbortController();
      async function read() {
        try {
          if (!view.sessionId || !object || object.kind !== KIND) throw new Error("附件会话或身份无效。");
          const requested = locator(view.target?.locator);
          const result = await host.operations.invoke("workbooks.metadata", { attachment_id: object.id, source_hash: object.version },
            { sessionId: view.sessionId, projectId: view.projectId, signal: controller.signal });
          const metadata = result.data;
          const sheet = requested?.sheet ?? metadata.sheets.find(s => s.state === "visible")?.name;
          if (!sheet || !metadata.sheets.some(s => s.name === sheet && s.state === "visible")) throw new Error("要查看的工作表不存在或不可见。");
          if (!controller.signal.aborted) setState({ key, metadata, sheet, requested });
        } catch (error) { if (!controller.signal.aborted) setState({ key, error: error instanceof Error ? error.message : "附件无法预览。" }); }
      }
      void read();
      return () => controller.abort();
    }, [key]);
    const sheet = state.key === key ? state.sheet : undefined;
    const previewKey = `${key}:${sheet}`;
    React.useEffect(() => {
      if (!sheet || !object) return undefined;
      const controller = new AbortController();
      async function read() {
        try {
          const [response, vendor] = await Promise.all([
            host.operations.invoke("workbooks.preview", { attachment_id: object.id, source_hash: object.version, sheet },
              { sessionId: view.sessionId, projectId: view.projectId, signal: controller.signal }),
            import(new URL("./vendor/workbook-runtime.js", import.meta.url).href),
          ]);
          if (response.data.sha256 !== object.version || response.data.attachment_id !== object.id) throw new Error("附件预览与原件版本不一致。");
          if (!controller.signal.aborted) { setRuntime(vendor); setLoaded({ key: previewKey, data: response.data }); }
        } catch (error) { if (!controller.signal.aborted) setLoaded({ key: previewKey, error: error instanceof Error ? error.message : "附件无法预览。" }); }
      }
      void read();
      return () => controller.abort();
    }, [previewKey]);
    const projection = loaded.key === previewKey ? loaded.data : null;
    const data = React.useMemo(() => projection && runtime ? fortuneSheets(projection, runtime.formatValue) : null, [projection, runtime]);
    React.useEffect(() => {
      if (!data || !grid.current) return undefined;
      // FortuneSheet listens to window resize; a resizable Dock can change
      // dimensions without resizing the window. Use that existing redraw path.
      let frame = 0;
      const observer = new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
      });
      observer.observe(grid.current);
      return () => { observer.disconnect(); cancelAnimationFrame(frame); };
    }, [data]);
    React.useEffect(() => {
      if (data && api.current && state.requested?.sheet === sheet) api.current.setSelection([
        { row: [state.requested.row, state.requested.row], column: [state.requested.column, state.requested.column] },
      ], { id: data[0].id });
    }, [data]);
    const error = state.key === key ? state.error || (loaded.key === previewKey ? loaded.error : null) : null;
    return h("section", { className: "dbfox-workbook-view", "aria-label": "工作簿预览" },
      h("div", { className: "dbfox-workbook-caption" }, "只读预览 · 原始文件未修改 · 公式仅显示缓存"),
      error ? h("div", { className: "dbfox-workbook-state", role: "alert" }, error)
        : data && runtime ? h("div", { className: "dbfox-workbook-grid", ref: grid }, h(runtime.Workbook, {
          key: previewKey, ref: api, data, lang: "zh", allowEdit: false, forceCalculation: false,
          showToolbar: false, showFormulaBar: true, showSheetTabs: false,
          cellContextMenu: ["copy"], headerContextMenu: [], sheetTabContextMenu: [],
        })) : h("div", { className: "dbfox-workbook-state", role: "status" }, "正在读取工作表…"),
      state.key === key && state.metadata ? h("div", { className: "dbfox-workbook-tabs", role: "tablist", "aria-label": "工作表" },
        ...state.metadata.sheets.map(s => h("button", { key: s.name, type: "button", role: "tab", "aria-selected": s.name === sheet,
          tabIndex: s.name === sheet ? 0 : -1, disabled: s.state !== "visible",
          onKeyDown: event => {
            const visible = state.metadata.sheets.filter(item => item.state === "visible");
            const index = visible.findIndex(item => item.name === s.name);
            const next = event.key === "Home" ? 0 : event.key === "End" ? visible.length - 1
              : event.key === "ArrowRight" ? (index + 1) % visible.length
              : event.key === "ArrowLeft" ? (index - 1 + visible.length) % visible.length : -1;
            if (next >= 0) {
              event.preventDefault();
              const name = visible[next].name;
              [...event.currentTarget.parentElement.children].find(button => button.textContent === name)?.focus();
              setState(previous => ({ ...previous, sheet: name, requested: null }));
            }
          }, onClick: () => setState(previous => ({ ...previous, sheet: s.name, requested: null })) }, s.name)),
      ) : null,
      h("small", { className: "dbfox-workbook-caption" }, "图表、图片及部分高级格式暂不展示。预览选表不改变分析口径。"),
    );
  }
  for (const file of typeof document === "undefined" ? [] : ["workbook.css", "vendor/workbook-runtime.css"]) {
    const link = document.createElement("link"); link.rel = "stylesheet"; link.href = new URL(file, import.meta.url).href;
    link.dataset.dbfoxDlc = host.dlcId; document.head.appendChild(link);
  }
  host.dockViews.register({ viewType: WORKBOOK_VIEW_TYPE, attachmentExtensions: ["xlsx"], preferredWidth: 680,
    icon: () => h(host.ui.ResourceIcon, { name: "workbook.xlsx", kind: "spreadsheet", size: 16 }), resolveTitle: view => view.title,
    isVisible: (view, context) => (!view.projectId || view.projectId === context.activeProjectId) && view.stateKey === context.workbenchScopeId,
    render: view => h(WorkbookDock, { view }),
  });
  return (source, sessionId) => host.dockViews.open({
    viewKey: `attachment:${sessionId}:${source.attachment_id}`, viewType: WORKBOOK_VIEW_TYPE, title: "原始工作簿", closeable: true,
    sessionId, stateKey: host.workbench.currentScopeId(), target: { type: "object",
      object: { kind: KIND, id: source.attachment_id, version: source.content_sha256 },
      locator: JSON.stringify({ sheet: source.sheet, row: source.header_row, column: 0 }) },
  });
}
